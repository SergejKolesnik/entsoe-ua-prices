import os
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from dotenv import load_dotenv
import pandas as pd

# Завантажуємо змінні з .env
load_dotenv()

def get_ua_dam_prices():
    api_key = os.getenv('ENTSOE_TOKEN')
    url = "https://web-api.tp.entsoe.eu/api"
    
    # Визначаємо період: сьогодні (весь день у UTC)
    # ENTSO-E вимагає формат YYYYMMDDHH00
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    
    params = {
        'securityToken': api_key,
        'documentType': 'A44',      # Price Document
        'processType': 'A01',       # Day Ahead
        'in_Domain': '10Y1001C--00003F',  # UA-IPS
        'out_Domain': '10Y1001C--00003F',
        'periodStart': today.strftime('%Y%m%d%H%M'),
        'periodEnd': tomorrow.strftime('%Y%m%d%H%M')
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status() # Перевірка на помилки HTTP
        
        # Парсинг XML
        root = ET.fromstring(response.content)
        
        # Простір імен ENTSO-E
        ns = {'ns': 'urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0'}
        
        data = []
        for point in root.findall('.//ns:Point', ns):
            pos = int(point.find('ns:position', ns).text)
            price = float(point.find('ns:price.amount', ns).text)
            # Розраховуємо час (ENTSO-E дає ціну на кожну годину)
            hour_time = today + timedelta(hours=pos-1)
            data.append({"Time (UTC)": hour_time, "Price (EUR/MWh)": price})
        
        df = pd.DataFrame(data)
        return df

    except Exception as e:
        return f"Сталася помилка: {e}"

if __name__ == "__main__":
    prices_df = get_ua_dam_prices()
    if isinstance(prices_df, pd.DataFrame):
        print("Ціни РДН для України (UA-IPS) на сьогодні:")
        print(prices_df.to_string(index=False))
    else:
        print(prices_df)
