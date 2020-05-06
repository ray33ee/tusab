rem Batch file to deploy python script as executable, copy config files, and rename to tusab

pyinstaller -y main.py

copy config.json .\dist\main\config.json

rename .\dist\main\main.exe tusab.exe