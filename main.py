import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import csv

def get_exchange_rate():
    """Отримує актуальний курс EUR/UAH від НБУ"""
    try:
        url = "https://bank.gov.ua/NBUStatService/v1/statdirectory/exchange?valcode=EUR&json"
        res = requests.get(url)
        return res.json()[0]['rate']
    except:
        return 45.5  # Резервний курс

def fetch_prices(date_target, api_key):
    url = "https://web-api.tp.entsoe.eu/api"
    UA_DOMAIN = '10Y1001C--00003F'
    
    start = date_target.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    
    params = {
        'securityToken': api_key,
        'documentType': 'A44',
        'in_Domain': UA_DOMAIN,
        'out_Domain': UA_DOMAIN,
        'periodStart': start.strftime('%Y%m%d%H%M'),
        'periodEnd': end.strftime('%Y%m%d%H%M')
    }
    
    response = requests.get(url, params=params)
    if response.status_code == 200:
        root = ET.fromstring(response.content)
        ns = {'ns': 'urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0'}
        return root.findall('.//ns:Point', ns), start.date()
    return None, None

def save_to_csv(points, date_val):
    if not points: return
    
    rate = get_exchange_rate()
    file_exists = os.path.isfile('prices_history.csv')
    
    with open('prices_history.csv', mode='a', newline='') as file:
        writer = csv.writer(file)
        if not file_exists:
            writer.writerow(['Date', 'Hour', 'Price_EUR_MWh', 'Price_UAH_MWh', 'Rate_NBU'])
        
        for point in points:
            pos = point.find('{*}position').text
            price_eur = float(point.find('{*}price.amount').text)
            price_uah = round(price_eur * rate, 2)
            hour = f"{int(pos)-1:02d}:00"
            writer.writerow([date_val, hour, price_eur, price_uah, rate])

if __name__ == "__main__":
    token = os.getenv('ENTSOE_TOKEN')
    now = datetime.utcnow()
    
    # Спочатку пробуємо на завтра
    points, date_val = fetch_prices(now + timedelta(days=1), token)
    
    if not points:
        print("На завтра даних ще немає, завантажуємо на сьогодні...")
        points, date_val = fetch_prices(now, token)
    
    if points:
        save_to_csv(points, date_val)
        print(f"Дані за {date_val} успішно збережені.")
    else:
        print("Помилка: дані недоступні.")
