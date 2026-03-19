import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import csv

def get_ua_prices():
    api_key = os.getenv('ENTSOE_TOKEN')
    url = "https://web-api.tp.entsoe.eu/api"
    
    # Код енергосистеми України (ОЕС)
    UA_DOMAIN = '10Y1001C--00003F'
    EUR_TO_UAH = 45.5  # Орієнтовний курс, пізніше автоматизуємо
    
    # Беремо дані на завтра (бо це РДН - ринок "на добу наперед")
    # Якщо запуск вранці, беремо на сьогодні.
    now = datetime.utcnow()
    start = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    
    params = {
        'securityToken': api_key,
        'documentType': 'A44',      # Price Document
        'processType': 'A01',       # Day Ahead
        'in_Domain': UA_DOMAIN,
        'out_Domain': UA_DOMAIN,
        'periodStart': start.strftime('%Y%m%d%H%M'),
        'periodEnd': end.strftime('%Y%m%d%H%M')
    }

    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            root = ET.fromstring(response.content)
            ns = {'ns': 'urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0'}
            
            # Перевіряємо, чи є взагалі дані у відповіді
            points = root.findall('.//ns:Point', ns)
            if not points:
                print(f"Дані для України на {start.date()} ще не опубліковані або відсутні.")
                return

            file_exists = os.path.isfile('prices_history.csv')
            with open('prices_history.csv', mode='a', newline='') as file:
                writer = csv.writer(file)
                if not file_exists:
                    writer.writerow(['Date', 'Hour', 'Price_EUR_MWh', 'Price_UAH_MWh'])
                
                for point in points:
                    pos = point.find('ns:position', ns).text
                    price_eur = float(point.find('ns:price.amount', ns).text)
                    price_uah = round(price_eur * EUR_TO_UAH, 2)
                    hour = f"{int(pos)-1:02d}:00"
                    writer.writerow([start.date(), hour, price_eur, price_uah])
            
            print(f"Дані за {start.date()} успішно додано.")
        else:
            print(f"Помилка API: {response.status_code}")
    except Exception as e:
        print(f"Помилка: {e}")

if __name__ == "__main__":
    get_ua_prices()
