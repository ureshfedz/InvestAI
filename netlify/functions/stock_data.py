import json
import pandas as pd
from datetime import datetime
from websocket import create_connection

def create_msg(ws, fun, arg):
    """Send a message to WebSocket"""
    ms = json.dumps({"m": fun, "p": arg})
    msg = "~m~" + str(len(ms)) + "~m~" + ms
    ws.send(msg)

def format_data(data):
    """Format received WebSocket data into structured format"""
    try:
        start = data.find('"s":[')
        end = data.find(',"ns":')
        if start == -1 or end == -1:
            return None
        
        final_data = json.loads(data[start + 4:end])
        stock_data = []
        
        for item in final_data:
            if "v" in item and len(item["v"]) >= 6:
                timestamp = item["v"][0]
                open_price = item["v"][1]
                high_price = item["v"][2]
                low_price = item["v"][3]
                close_price = item["v"][4]
                volume = int(item["v"][5])
                dt = datetime.fromtimestamp(timestamp)
                
                stock_data.append({
                    'Date': dt.strftime('%Y-%m-%d'),
                    'Open': open_price,
                    'High': high_price,
                    'Low': low_price,
                    'Close': close_price,
                    'Volume': volume,
                    'Timestamp': timestamp
                })
        
        if stock_data:
            df = pd.DataFrame(stock_data).sort_values('Timestamp').reset_index(drop=True)
            df['Daily_Change'] = df['Close'].diff().round(2)
            df['Daily_Change_Pct'] = (df['Close'].pct_change() * 100).round(2)
            df['Day_Range'] = (df['High'] - df['Low']).round(2)
            df.drop('Timestamp', axis=1, inplace=True)
            return df
        else:
            return None
    except Exception as e:
        print(f"Error formatting data: {e}")
        return None

def fetch_stock_data(company_symbol):
    """Fetch stock data from TradingView WebSocket"""
    try:
        # Automatically append .N0000 if user didn't include it
        if not company_symbol.endswith(".N0000"):
            company_symbol += ".N0000"
        
        symbol_code = f"CSELK:{company_symbol}"
        socket_url = "wss://data.tradingview.com/socket.io/websocket"
        
        # WebSocket Connection
        ws = create_connection(socket_url)
        session_id = "cs_" + datetime.now().strftime('%H%M%S')
        
        # Send Subscription Messages
        create_msg(ws, "chart_create_session", [session_id, ""])
        create_msg(ws, "resolve_symbol", [session_id, "sds_sym_1", f"={{\"adjustment\":\"splits\",\"symbol\":\"{symbol_code}\"}}"])
        create_msg(ws, "create_series", [session_id, "sds_1", "s1", "sds_sym_1", "D", 10000, ""])
        
        # Receive Data
        stock_dataframe = None
        while True:
            res = ws.recv()
            if '"m":"timescale_update"' in res:
                stock_dataframe = format_data(res)
            if "series_completed" in res:
                break
        
        ws.close()
        
        if stock_dataframe is not None:
            # Convert DataFrame to dictionary for JSON response
            data_dict = stock_dataframe.to_dict('records')
            
            # Calculate summary statistics
            summary = {
                'total_days': len(stock_dataframe),
                'date_range': f"{stock_dataframe['Date'].iloc[0]} to {stock_dataframe['Date'].iloc[-1]}",
                'latest_price': round(stock_dataframe['Close'].iloc[-1], 2),
                'highest_price': round(stock_dataframe['High'].max(), 2),
                'lowest_price': round(stock_dataframe['Low'].min(), 2),
                'best_day': round(stock_dataframe['Daily_Change_Pct'].max(), 2),
                'worst_day': round(stock_dataframe['Daily_Change_Pct'].min(), 2),
                'symbol': company_symbol
            }
            
            return {
                'success': True,
                'data': data_dict,
                'summary': summary
            }
        else:
            return {
                'success': False,
                'error': 'No valid stock data found'
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def handler(event, context):
    """Netlify function handler"""
    try:
        # Handle CORS
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Headers': 'Content-Type',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
        }
        
        if event['httpMethod'] == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': headers,
                'body': ''
            }
        
        if event['httpMethod'] != 'POST':
            return {
                'statusCode': 405,
                'headers': headers,
                'body': json.dumps({'error': 'Method not allowed'})
            }
        
        # Parse request body
        body = json.loads(event['body'])
        symbol = body.get('symbol', '').strip().upper()
        
        if not symbol:
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'success': False, 'error': 'Please enter a valid company symbol'})
            }
        
        # Fetch stock data
        result = fetch_stock_data(symbol)
        
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps(result)
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Methods': 'GET, POST, OPTIONS'
            },
            'body': json.dumps({'success': False, 'error': str(e)})
        }