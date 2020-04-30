rem Batch file to deploy python script as executable, copy config files, and rename to tusab

pyinstaller -y main.py

copy config.json .\dist\main\config.json
copy credentials.json  .\dist\main\credentials.json
copy drive.pickle  .\dist\main\drive.pickle

rename .\dist\main\main.exe tusab.exe