import asyncio
import re
from datetime import datetime
from typing import Optional, Dict, Any, List
from playwright.async_api import async_playwright

BASE_URL = "https://delhihighcourt.nic.in"
DEFAULT_TIMEOUT_MS = 60_000

def _parse_date_from_text(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    m = re.search(r'(\d{2}-\d{2}-\d{4})', text)
    if m:
        try:
            return datetime.strptime(m.group(1), "%d-%m-%Y")
        except:
            return None
    return None

async def _safe_goto(page, url: str, retries: int = 3, timeout_ms: int = DEFAULT_TIMEOUT_MS):
    last_exc = None
    for attempt in range(retries):
        try:
            await page.goto(url, timeout=timeout_ms, wait_until="domcontentloaded")
            return
        except Exception as e:
            last_exc = e
            await asyncio.sleep(1 + attempt)
    # re-raise the last exception if all retries failed
    raise last_exc

async def fetch_case_details(
    case_type: str,
    case_number: str,
    case_year: str,
    captcha_text: Optional[str] = None,
    headless: bool = True,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> Dict[str, Any]:
    """
    Fetch case data from Delhi High Court case-number page.
    Returns dict: {status: "SUCCESS"/"NO_DATA"/"ERROR", data: [...], message: "...", raw_html: "..." (on error)}
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=["--disable-blink-features=AutomationControlled"])
        page = await browser.new_page()
        try:
            # 1) Open page (with retries)
            try:
                await _safe_goto(page, f"{BASE_URL}/app/case-number", retries=3, timeout_ms=timeout_ms)
            except Exception as e:
                return {"status": "ERROR", "message": f"Unable to reach court site: {e}"}

            # 2) Fill form - selects: try by value first, then label fallback
            try:
                async def _select(selector, value):
                    try:
                        await page.select_option(selector, value)
                    except Exception:
                        # fallback to selecting by label (visible text)
                        try:
                            await page.select_option(selector, {"label": value})
                        except Exception:
                            # ignore - the site might accept the visible text in other ways
                            pass

                await _select("#case_type", case_type)
                await page.fill("#case_number", case_number)
                await _select("#year", case_year)

                # CAPTCHA: if user provided captcha_text use it; else try reading span#captcha-code
                if captcha_text:
                    await page.fill("#captchaInput", captcha_text)
                else:
                    try:
                        # sometimes inner_text() can raise if element not present
                        captcha_span = await page.locator("#captcha-code").inner_text(timeout=3000)
                        captcha_span = captcha_span.strip() if captcha_span else ""
                        if captcha_span:
                            await page.fill("#captchaInput", captcha_span)
                        else:
                            return {"status": "ERROR", "message": "Unable to read CAPTCHA from page; please provide captcha_text (manual input)."}
                    except Exception:
                        return {"status": "ERROR", "message": "CAPTCHA not readable automatically; please provide captcha_text (manual input)."}

                # Submit
                await page.click("#search")
            except Exception as e:
                return {"status": "ERROR", "message": f"Error submitting form: {e}", "raw_html": await page.content()}

            # 3) Wait for table update
            table_selector = "#s_judgeTable"
            tbody_selector = f"{table_selector} tbody"

            # Basic wait for the table element to exist
            try:
                await page.wait_for_selector(table_selector, timeout=timeout_ms)
            except Exception:
                # maybe site structure changed or page didn't load; bail with raw_html
                return {"status": "ERROR", "message": "Search result table not found on page.", "raw_html": await page.content()}

            # First attempt: if DataTables shows a processing spinner, wait for it to appear (short) and then disappear.
            processing_selector = ".dataTables_processing"
            try:
                # short attempt to see processing indicator; if present wait for hidden
                await page.wait_for_selector(processing_selector, timeout=3000, state="visible")
                # now wait until it becomes hidden (table finished)
                await page.wait_for_selector(processing_selector, timeout=timeout_ms, state="hidden")
            except Exception:
                # spinner didn't show up within short time OR other timing; fallback to DOM-change detection below
                pass

            # DOM-change detection:
            # capture initial tbody HTML (if present)
            initial_html = ""
            try:
                if await page.locator(tbody_selector).count() > 0:
                    initial_html = await page.locator(tbody_selector).inner_html()
            except Exception:
                initial_html = ""

            # Wait for either:
            #  - tbody innerHTML to change (table got updated)
            #  - OR first row is present and its second td has non-empty text
            # We pass args as a single object to wait_for_function.
            try:
                await page.wait_for_function(
                    """
                    (args) => {
                        const sel = args.selector;
                        const initial = args.initial || '';
                        const tbody = document.querySelector(sel);
                        if (!tbody) return false;
                        // If DataTables explicitly shows "no data" cell, treat that as finished state.
                        const emptyCell = tbody.querySelector('td.dataTables_empty');
                        if (emptyCell && emptyCell.innerText && emptyCell.innerText.trim().length > 0) {
                            // if initial was different, return true; otherwise still return true because processing completed with no results
                            return true;
                        }
                        // check rows presence and second column text
                        const rows = Array.from(tbody.querySelectorAll('tr'));
                        if (rows.length > 0) {
                            const firstTds = Array.from(rows[0].querySelectorAll('td'));
                            if (firstTds.length >= 2 && firstTds[1].innerText && firstTds[1].innerText.trim().length > 0) {
                                return true;
                            }
                        }
                        // otherwise check if innerHTML changed (re-rendered)
                        try {
                            const cur = tbody.innerHTML;
                            if (cur !== initial) return true;
                        } catch (err) {
                            // ignore and keep waiting
                        }
                        return false;
                    }
                    """,
                    arg={"selector": tbody_selector, "initial": initial_html},
                    timeout=timeout_ms,
                )
            except Exception:
                # final fallback: if nothing happened within timeout, return friendly message
                return {"status": "ERROR", "message": "Timed out waiting for search results. The court website may be slow or unavailable right now." , "raw_html": await page.content()}

            # 4) Now check if "No data available" is present
            try:
                if await page.locator(f"{tbody_selector} td.dataTables_empty").count() > 0:
                    return {"status": "NO_DATA", "message": "No matching records found. Please re-check the inputs and try again."}
            except Exception:
                # ignore and continue if this check fails
                pass

            # 5) Extract rows in one snapshot (evaluate in browser)
            try:
                rows = await page.evaluate(
                    """(sel) => {
                        const out = [];
                        const table = document.querySelector(sel);
                        if (!table) return out;
                        const tbody = table.querySelector('tbody');
                        if (!tbody) return out;
                        const rowElems = Array.from(tbody.querySelectorAll('tr'));
                        for (const r of rowElems) {
                            const tds = Array.from(r.querySelectorAll('td'));
                            // Expected columns: 0=S.No, 1=Case No, 2=Date(links), 3=Party, 4=Corrigendum
                            const case_no = (tds[1] && tds[1].innerText) ? tds[1].innerText.trim() : '';
                            const case_link_el = (tds[1] && tds[1].querySelector('a')) ? tds[1].querySelector('a') : null;
                            const case_link = case_link_el ? case_link_el.href : null;
                            const dateCell = tds[2] || null;
                            const links = [];
                            if (dateCell) {
                                const aEls = Array.from(dateCell.querySelectorAll('a'));
                                for (const a of aEls) {
                                    links.push({ text: (a.innerText || '').trim(), href: a.href });
                                }
                                // if there is plain text date before links, include it as well (textContent)
                                if (links.length === 0 && dateCell.textContent) {
                                    // try to extract any date-like text
                                    links.push({ text: dateCell.textContent.trim(), href: null });
                                }
                            }
                            const party = (tds[3] && tds[3].innerText) ? tds[3].innerText.trim() : '';
                            const corrigendum = (tds[4] && tds[4].innerText) ? tds[4].innerText.trim() : '';
                            out.push({ case_no, case_link, party, corrigendum, links });
                        }
                        return out;
                    }
                    """,
                    table_selector,
                )
            except Exception as e:
                return {"status": "ERROR", "message": f"Failed to extract rows: {e}", "raw_html": await page.content()}

            # 6) Post-process rows: parse dates from link text/href, sort links and rows
            processed: List[Dict[str, Any]] = []
            for r in rows:
                links_info = []
                for link in r.get("links", []):
                    txt = link.get("text") or ""
                    href = link.get("href") or ""
                    parsed_dt = _parse_date_from_text(txt) or _parse_date_from_text(href)
                    doc_type = None
                    if href and re.search(r'\.pdf($|\?)', href, re.I) or 'pdf' in txt.lower():
                        doc_type = 'pdf'
                    elif href and re.search(r'\.txt($|\?)', href, re.I) or 'txt' in txt.lower():
                        doc_type = 'txt'
                    links_info.append({
                        "text": txt,
                        "url": href,
                        "date_obj": parsed_dt,
                        "date": parsed_dt.isoformat() if parsed_dt else None,
                        "doc_type": doc_type,
                    })

                # sort links by date (newest first). unknown dates go to the end.
                links_info.sort(key=lambda x: x["date_obj"] or datetime.min, reverse=True)

                latest_date_iso = links_info[0]["date"] if links_info and links_info[0]["date"] else None

                processed.append({
                    "case_no": r.get("case_no"),
                    "case_link": r.get("case_link"),
                    "party": r.get("party"),
                    "corrigendum": r.get("corrigendum"),
                    "judgment_links": [
                        {"text": li["text"], "url": li["url"], "date": li["date"], "doc_type": li["doc_type"]}
                        for li in links_info
                    ],
                    "latest_judgment_date": latest_date_iso,
                })

            # 7) If we have parseable judgment dates, filter to the latest YEAR (per task)
            years = [d["latest_judgment_date"][:4] for d in processed if d["latest_judgment_date"]]
            if years:
                latest_year = max(years)
                processed = [d for d in processed if d["latest_judgment_date"] and d["latest_judgment_date"].startswith(latest_year)]

            # Sort final results by latest_judgment_date descending (unknowns last)
            processed.sort(key=lambda x: x["latest_judgment_date"] or "", reverse=True)

            return {"status": "SUCCESS", "data": processed}

        except Exception as e:
            try:
                raw = await page.content()
            except:
                raw = "<unavailable>"
            return {"status": "ERROR", "message": f"Unexpected error: {e}", "raw_html": raw}
        finally:
            await browser.close()

