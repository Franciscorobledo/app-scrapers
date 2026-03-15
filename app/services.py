# Search Service Logic

class SearchService:
    def __init__(self, data):
        self.data = data

    def search(self, query):
        results = []
        for item in self.data:
            if query.lower() in item.lower():
                results.append(item)
        return results

    def get_results(self, query):
        return self.search(query)
