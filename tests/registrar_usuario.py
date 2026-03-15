"""Script para registrar usuarios de Telegram (capturar chat_id)."""
import sys
sys.path.insert(0, 'src')

import json
import requests
from config_loader import ConfigLoader

config = ConfigLoader()
token = config.telegram_bot_token

print("Consultando mensajes recientes del bot...")
url = f"https://api.telegram.org/bot{token}/getUpdates"
r = requests.get(url)
data = r.json()

if not data.get('ok'):
    print("Error:", data)
    sys.exit(1)

results = data.get('result', [])
if not results:
    print("No hay mensajes. Asegúrate de enviar /start al bot primero.")
    sys.exit(0)

registro = {}
for update in results:
    if 'message' in update:
        chat = update['message']['chat']
        chat_id = chat['id']
        nombre = chat.get('first_name', '') + ' ' + chat.get('last_name', '')
        print(f"  Usuario encontrado: {nombre.strip()} -> chat_id={chat_id}")
        # Registrar con un celular genérico (se puede mapear después)
        registro[f"usuario_{chat_id}"] = chat_id

# Guardar en registro_usuarios.json
registro_path = 'data/registro_usuarios.json'

# Leer el mapeo de personal para vincular
try:
    import pandas as pd
    personal = pd.read_csv('data/maestro_personal.csv')
    # Asignar el primer chat_id encontrado a todos los del personal
    primer_chat_id = list(registro.values())[0] if registro else None
    if primer_chat_id:
        registro_final = {}
        for _, p in personal.iterrows():
            celular = str(p['numero_celular']).strip()
            registro_final[celular] = primer_chat_id
        
        with open(registro_path, 'w') as f:
            json.dump(registro_final, f, indent=2)
        
        print(f"\nRegistro guardado en {registro_path}")
        print(f"Todos los números del personal apuntan a chat_id={primer_chat_id}")
        print("(Para producción, cada operario se registraría individualmente)")
    else:
        print("No se encontró ningún chat_id.")
except Exception as e:
    print(f"Error: {e}")
