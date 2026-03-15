import requests
from bs4 import BeautifulSoup

class SodimacScraper:
    def __init__(self):
        self.base_url = 'https://www.sodimac.cl'

    def get_products(self, category_url):
        response = requests.get(category_url)
        soup = BeautifulSoup(response.content, 'html.parser')
        products = soup.find_all('div', class_='product-item')  # Update based on the actual HTML structure
        product_list = []

        for product in products:
            title = product.find('h2', class_='product-title').text.strip()  # Update class as necessary
            price = product.find('span', class_='product-price').text.strip()  # Update class as necessary
            product_list.append({'title': title, 'price': price})

        return product_list

    def scrape(self):
        # Example usage
        category_url = f'{self.base_url}/categoria/instrumentos'
        products = self.get_products(category_url)
        return products

if __name__ == '__main__':
    scraper = SodimacScraper()
    scraped_data = scraper.scrape()
    print(scraped_data)