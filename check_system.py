#!/usr/bin/env python3

import subprocess
import requests
import time
import os

def check_processes():
    print("Checking processes...")
    
    try:
        result = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
        processes = result.stdout
        
        main_count = len([line for line in processes.split('\n') if 'main.py' in line and 'grep' not in line])
        bot_count = len([line for line in processes.split('\n') if 'giveaway_bot.py' in line and 'grep' not in line])
        uvicorn_count = len([line for line in processes.split('\n') if 'uvicorn' in line and 'grep' not in line])
        
        print(f"  Main processes: {main_count}")
        print(f"  Bot processes: {bot_count}")
        print(f"  Web processes: {uvicorn_count}")
        
        if main_count > 0:
            print("   System is running")
            return True
        else:
            print("   System is not running")
            return False
            
    except Exception as e:
        print(f"   Error checking processes: {e}")
        return False

def check_web_interface():
    print("Checking web interface...")
    
    try:
        response = requests.get('http://localhost:3001/', timeout=5)
        if response.status_code == 200:
            print("   Web interface is accessible")
            return True
        else:
            print(f"   Web interface returned status {response.status_code}")
            return False
    except Exception as e:
        print(f"   Web interface not accessible: {e}")
        return False

def check_environment():
    print("Checking environment...")
    
    required_vars = ['TELEGRAM_TOKEN', 'DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print(f"   Missing variables: {', '.join(missing_vars)}")
        return False
    else:
        print("   All required environment variables are set")
        return True

def main():
    print("Giveaway Bot System Check")
    print("=" * 40)
    
    checks = [
        ("Environment Variables", check_environment),
        ("System Processes", check_processes),
        ("Web Interface", check_web_interface)
    ]
    
    all_passed = True
    for check_name, check_func in checks:
        print(f"\n{check_name}:")
        if not check_func():
            all_passed = False
    
    print("\n" + "=" * 40)
    if all_passed:
        print("All checks passed! System is working correctly.")
        print("\nWeb interface: http://localhost:3001")
        print("Prize URLs: https://ahgan.coonlink.com/giftgiver/card/show/code/{security_code}")
        print("\nUse 'python3 manage.py status' to check system status")
    else:
        print("Some checks failed. Please fix the issues above.")
        print("\nTry: python3 manage.py restart")

if __name__ == "__main__":
    main()
