import re
from pathlib import Path

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

DATA_DIR.mkdir(exist_ok=True)

PAGES = {

    # -------------------------
    # Main
    # -------------------------
    "home.txt":
        "https://sensrs.com/",

    "about.txt":
        "https://sensrs.com/about-us/",

    "vision_mission.txt":
        "https://sensrs.com/visionandmission/",

    "projects.txt":
        "https://sensrs.com/projects/",

    "policies.txt":
        "https://sensrs.com/policy/",


    # -------------------------
    # Careers / Programmes
    # -------------------------
    "internships.txt":
        "https://sensrs.com/internship/",

    "phd.txt":
        "https://sensrs.com/phd-programme/",

    "opportunities.txt":
        "https://sensrs.com/opportunities/",


    # -------------------------
    # Services
    # -------------------------
    "services.txt":
        "https://sensrs.com/consultancy-services/",

    "drone_services.txt":
        "https://sensrs.com/consultancy-services/drone-services/",

    "dgps_services.txt":
        "https://sensrs.com/consultancy-services/dgps-service/",

    "bathymetry_services.txt":
        "https://sensrs.com/consultancy-services/bathymetry-survey/",

    "web_development.txt":
        "https://sensrs.com/consultancy-services/web-development/",

    "dashboard_development.txt":
        "https://sensrs.com/consultancy-services/dashboards-analytics/",

    "app_development.txt":
        "https://sensrs.com/consultancy-services/app-development/",

    "ip_services.txt":
        "https://sensrs.com/consultancy-services/ip-services/",

    "tls_services.txt":
        "https://sensrs.com/consultancy-services/tls-survey/",

    "hyperspectral_services.txt":
        "https://sensrs.com/consultancy-services/hyperspectral-sensor/",


    # -------------------------
    # Events / Outreach
    # -------------------------
    "events.txt":
        "https://sensrs.com/events/",

    "gallery.txt":
        "https://sensrs.com/photo-gallery/",

    "video_gallery.txt":
        "https://sensrs.com/video-gallery/",

    "press_news.txt":
        "https://sensrs.com/press-and-news/",

    "newsletter.txt":
        "https://sensrs.com/newsletter/",

    "publications.txt":
        "https://sensrs.com/publications/",


    # -------------------------
    # Contact
    # -------------------------
    "contact.txt":
        "https://sensrs.com/contact/",
}


def clean_text(html):
    soup = BeautifulSoup(html, "html.parser")

    # Remove elements that are not useful for the knowledge base
    for element in soup([
        "script",
        "style",
        "noscript",
        "svg",
        "nav",
        "header",
        "footer"
    ]):
        element.decompose()

    # Find the main content
    main = soup.find("main")

    if main:
        text = main.get_text("\n")
    else:
        text = soup.get_text("\n")

    # Clean whitespace
    lines = []

    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()

        if line:
            lines.append(line)

    return "\n\n".join(lines)


def scrape_page(filename, url):

    print(f"\nFetching: {url}")

    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "SEnSRS-AI-Bot/1.0"
        }
    )

    response.raise_for_status()

    text = clean_text(response.text)

    output_file = DATA_DIR / filename

    output_file.write_text(
        text,
        encoding="utf-8"
    )

    print(f"Saved: {output_file}")
    print(f"Characters: {len(text)}")


def main():

    print("Starting SEnSRS website collection...")

    for filename, url in PAGES.items():

        try:
            scrape_page(filename, url)

        except Exception as error:
            print(f"ERROR: {error}")

    print("\nWebsite collection completed.")


if __name__ == "__main__":
    main()