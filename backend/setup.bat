@echo off
echo === QueueLess setup ===
python -m venv venv
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
echo.
echo === Running tests ===
pytest
echo.
echo Setup done. Ab run.bat double-click karo.
pause
