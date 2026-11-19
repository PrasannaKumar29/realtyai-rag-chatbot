"""Capture only the five approved public informational sources, visibly."""

from .wasalt_paths import REPO_ROOT, DATA_ROOT, MANUAL_EXPORTS, resolve_data_path

from datetime import datetime, timezone
import json
from pathlib import Path
import time

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from .test_wasalt_browser import records
from .wasalt_extract_batch import challenge_detected


ROOT = REPO_ROOT
SOURCES = (
    ("homepage", "https://wasalt.sa/en"),
    ("corporate", "https://wasalt.sa/en/corporate"),
    ("project", "https://wasalt.sa/en/project/Riyadh/shams-al-riyadh-100325"),
    ("auction_terms", "https://wasalt.sa/en/s/terms-n-conditions-for-auction"),
    ("auction_landing", "https://auction.wasalt.sa/en"),
)
OUT = DATA_ROOT / "informational/source_data"


def block_text(html):
    soup = BeautifulSoup(html, "html.parser")
    for node in soup.select("script,style,nav,header,footer,form,button,input,svg"):
        node.decompose()
    return soup.get_text("\n", strip=True)


def heading_blocks(page, names):
    return page.locator("h1,h2,h3,h4").evaluate_all("""(nodes, names) => nodes.filter(n => names.includes(n.innerText.trim().replace(/\\s+/g,' '))).map(n => {
        const parents=[]; let p=n.parentElement;
        for(let i=0;i<4 && p;i++,p=p.parentElement) {
            if(p.innerText.length<12000) parents.push({text:p.innerText,html:p.outerHTML});
        }
        return {heading:n.innerText.trim(),parents};
    })""", names)


def main():
    for key, _ in SOURCES:
        if (OUT / f"{key}.json").exists():
            raise FileExistsError("Source capture exists; refusing to overwrite")
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(service_workers="block")
        try:
            for index, (key, url) in enumerate(SOURCES):
                if index:
                    time.sleep(3)
                page = context.new_page()
                # No document navigation beyond the approved source, including
                # links, authentication, listing pages, or automatic refreshes.
                navigated = False

                def guard(route):
                    nonlocal navigated
                    request = route.request
                    if request.is_navigation_request():
                        if request.frame != page.main_frame or request.url != url or navigated:
                            route.abort()
                            return
                        navigated = True
                    route.continue_()

                page.route("**/*", guard)
                try:
                    response = page.goto(url, wait_until="domcontentloaded", timeout=45000)
                    status = response.status if response else None
                    title = page.title()
                    if challenge_detected(page, status, title):
                        raise RuntimeError("Access restriction detected; stopping without retry")
                    if status != 200 or page.url != url:
                        raise RuntimeError(f"Unexpected response for {key}: {status}")
                    payload = {"source_url": url, "extracted_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"), "http_status": status, "page_title": title}
                    parsed = [json.loads(value) for value in page.locator('script[type="application/ld+json"]').all_text_contents()]
                    if key == "homepage":
                        payload["faq_records"] = [record for value in parsed for record in records(value) if record.get("@type") == "FAQPage"]
                        payload["section_candidates"] = heading_blocks(page, ["List your daily rentals with Wasalt", "Grow your business. Connect with clients easily.", "Why List Your Property with Wasalt?", "Find the right property for your needs"])
                    elif key == "corporate":
                        payload["sections"] = []
                        for selector in ('[class*="heroBannerContainer"]', '[class*="searchHeading"]', '[class*="ContentPart"]'):
                            for html in page.locator(selector).evaluate_all("nodes => nodes.map(n=>n.outerHTML)"):
                                payload["sections"].append({"selector": selector, "text": block_text(html)})
                    elif key == "project":
                        payload["json_ld"] = [record for value in parsed for record in records(value) if record.get("@type") == "SingleFamilyResidence"]
                        payload["about_candidates"] = heading_blocks(page, ["About Project"])
                        payload["attribute_candidates"] = page.locator('[class*="projectDetail"], [class*="ProjectDetail"], [class*="projectOverview"], [class*="ProjectOverview"]').evaluate_all("nodes=>nodes.filter(n=>n.innerText.length<18000).map(n=>({tag:n.tagName,cls:n.className,text:n.innerText}))")
                    elif key == "auction_terms":
                        payload["article_candidates"] = heading_blocks(page, page.locator("h1,h2,h3,h4").all_text_contents()[2:])
                    else:
                        # Exclude auction cards, assets, prices, registrations,
                        # navigation/footer, and every individual auction link.
                        payload["explanation_candidates"] = heading_blocks(page, ["About Wasalt Auctions", "How It Works", "How it works", "Frequently Asked Questions", "Why Wasalt Auctions?"])
                        payload["faq_records"] = [record for value in parsed for record in records(value) if record.get("@type") == "FAQPage"]
                        payload["has_public_explanations"] = bool(payload["explanation_candidates"] or payload["faq_records"])
                    with (OUT / f"{key}.json").open("x", encoding="utf-8") as handle:
                        json.dump(payload, handle, ensure_ascii=False, indent=2)
                        handle.write("\n")
                    print(key, status, "source capture saved", flush=True)
                finally:
                    page.close()
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
