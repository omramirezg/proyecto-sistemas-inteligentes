import sys

try:
    with open('log_temp.txt', 'r', encoding='utf8', errors='ignore') as f:
        lines = f.readlines()
        
    for i, line in enumerate(lines[-100:]):
        if 'Traceback' in line or 'Event loop is closed' in line:
            print("".join(lines[-100+i: -100+i+20]))
            break
except Exception as e:
    print(e)
