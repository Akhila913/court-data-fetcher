# Delhi High Court Case Fetcher

A Django + Playwright web application to fetch and display case metadata and the latest orders/judgments from the **Delhi High Court**.

---

## Court Chosen
- **Delhi High Court**
- Official case search page: [https://delhihighcourt.nic.in/app/case-number](https://delhihighcourt.nic.in/app/case-number)

---

## Features
- Simple HTML form for:
  - **Case Type** (dropdown)
  - **Case Number** (numeric/text)
  - **Filing Year** (dropdown)
- Automatically solves simple text CAPTCHA displayed on the site (no external service).
- Scrapes and displays:
  - Parties’ names
  - Latest judgment/order date
  - Corrigendum info
  - Direct PDF/TXT download links for judgments/orders
- Stores each query in the database with raw HTML for debugging.
- Gracefully handles:
  - Wrong inputs (friendly “No matching records” message)
  - Site downtime or slow responses
- Minimal, mobile-friendly UI with blurred court background image.

---

## CAPTCHA Strategy
- The Delhi High Court site uses a **simple text-based CAPTCHA** displayed in `<span id="captcha-code">`.
- The scraper:
  1. Reads the inner text from the CAPTCHA span directly.
  2. Fills it into the CAPTCHA input field.
- **No third-party OCR or bypassing services used** — purely reading visible text.

---

## Setup Steps

### 1. Clone the repository
git clone https://github.com/your-username/court-fetcher.git
cd court-fetcher

### 2. Create a virtual environment
python -m venv venv   
source venv/Scripts/activate       

### 3. Install dependencies
pip install -r requirements.txt
### 4. Install Playwright browsers

playwright install
### 5. Apply migrations
python manage.py migrate
### 6. Run the development server
python manage.py runserver
The app will be available at: http://localhost:8000

### Sample Test Data
Case Type: W.P.(C)
Case Number: 3760
Year: 2024

To view the stored queries in the SQLite database (`QueryLog` table), go to the Django admin page after logging in:  
[http://localhost:8000/admin/fetcher/querylog/](http://localhost:8000/admin/fetcher/querylog/)
