import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

def get_ua_prices():
    # Отримуємо токен із секретів GitHub
    api_key = os.getenv('ENTSOE_TOKEN')
    url = "https://web-api.tp.entsoe.eu/api"
    
    # Визначаємо час: сьогодні
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
            print(f"--- Ціни РДН на {start.date()} ---")
            root = ET.fromstring(response.content)
            ns = {'ns': 'urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0'}
            
            for point in root.findall('.//ns:Point', ns):
                pos = point.find('ns:position', ns).text
                price = point.find('ns:price.amount', ns).text
                print(f"Година {int(pos)-1:02d}:00 | Ціна: {price} EUR")
        else:
            print(f"Помилка API: {response.status_code}")
            print(response.text)
    except Exception as e:
        print(f"Помилка: {e}")

if __name__ == "__main__":
    get_ua_prices()
