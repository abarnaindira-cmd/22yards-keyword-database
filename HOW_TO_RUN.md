# How to Run – Amazon & Flipkart Keyword Database

Project folder:
`D:\22yards_keyword_database_competitor_ready\22yards_keyword_database`

## 1. One-time setup

1. Make sure **MySQL** is running.
2. Check the `.env` file in the project folder has your MySQL login and `GROQ_API_KEY`.
3. Install packages (run once):

```
cd D:\22yards_keyword_database_competitor_ready\22yards_keyword_database
pip install -r requirements.txt
pip install groq pandas
```

## 2. Start the backend (Terminal 1)

```
cd D:\22yards_keyword_database_competitor_ready\22yards_keyword_database
uvicorn app.main:app --reload --port 8001
```

Wait for: `Application startup complete`
Check: http://127.0.0.1:8001/health

## 3. Start the frontend (Terminal 2)

```
cd D:\22yards_keyword_database_competitor_ready\22yards_keyword_database\ui
python -m http.server 5500 --bind 127.0.0.1
```

Open in browser: http://127.0.0.1:5500/index.html

Keep the backend on port **8001**. The UI only talks to port 8001.

## 4. Download final product titles

1. Click **Open Amazon Workspace**.
2. Upload the product Excel.
3. Click **Download Final Data Excel**.

The file has: `product_name`, `sku_id`, `final_product_title`, `all_keywords`.

## 5. Stop

Press `Ctrl+C` in both terminals.

## Common problems

| Problem | Fix |
|---|---|
| UI does not show "MySQL Databases Connected" | Start the backend (Terminal 1) and MySQL. |
| `Could not import module "app.main"` | Run uvicorn from the project folder, not the `ui` folder. |
| Browser shows "404" or a folder list | Run the frontend command from inside the `ui` folder. |
| `No module named 'groq'` or `'pandas'` | `pip install groq pandas` |
| Port already in use | Close the old terminal (`Ctrl+C`) and start again. |
| Old page text after an update | Press `Ctrl+F5` in the browser. |
