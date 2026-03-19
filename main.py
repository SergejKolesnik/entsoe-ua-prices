import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import csv

def get_ua_prices():
    api_key = os.getenv('ENTSOE_TOKEN')
    url = "https://web-api.tp.entsoe.eu/api"
    
    start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    
    params = {
        'securityToken': api_key,
        'documentType': 'A44',
        'in_Domain': '10Y1001C--00003F',
        'out_Domain': '10Y1001C--00003F',
        'periodStart': start.strftime('%Y%m%d%H%M'),
        'periodEnd': end.strftime('%Y%m%d%H%M')
    }

    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            ns = {'ns': 'urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0'}
            
            # Створюємо або дописуємо у CSV
            file_exists = os.path.isfile('prices_history.csv')
            with open('prices_history.csv', mode='a', newline='') as file:
                writer = csv.writer(file)
                if not file_exists:
                    writer.writerow(['Date', 'Hour', 'Price_EUR_MWh']) # Заголовки
                
                for point in root.findall('.//ns:Point', ns):
                    pos = point.find('ns:position', ns).text
                    price = point.find('ns:price.amount', ns).text
                    hour = f"{int(pos)-1:02d}:00"
                    writer.writerow([start.date(), hour, price])
            
            print(f"Дані за {start.date()} успішно збережено в CSV.")
        else:
            print(f"Помилка API: {response.status_code}")
    except Exception as e:
        print(f"Помилка: {e}")

if __name__ == "__main__":
    get_ua_prices()
