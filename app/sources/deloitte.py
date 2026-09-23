from app.sources.successfactors import SuccessFactorsSource


class DeloitteSource(SuccessFactorsSource):
    name = company = 'Deloitte'
    url = 'https://empleo.es.deloitte.com/search/'

    def listing_url(self, offset):
        if not offset:
            return self.url
        return f'https://empleo.es.deloitte.com/tile-search-results/?q=&sortColumn=referencedate&sortDirection=desc&startrow={offset}'
