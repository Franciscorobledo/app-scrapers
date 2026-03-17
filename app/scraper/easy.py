"""Easy.cl scraper example.

This module provides a small example scraper class that fetches page content
from Easy.cl and parses the response with BeautifulSoup.
"""

import requests
from bs4 import BeautifulSoup

class EasyScraper:
    def __init__(self, url):
        self.url = url
        self.data = []

    def fetch_data(self):
        response = requests.get(self.url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # Add scraping logic here
            self.data.append(soup)

    def parse_data(self):
        # Implement parsing logic to extract required information
        pass

if __name__ == "__main__":
    easy_scraper = EasyScraper("http://example.com")
    easy_scraper.fetch_data()
