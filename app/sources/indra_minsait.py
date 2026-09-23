from app.sources.successfactors import SuccessFactorsSource


class IndraMinsaitSource(SuccessFactorsSource):
    name = company = 'Indra / Minsait'
    url = 'https://careers.indragroup.com/search/?q=&optionsFacetsDD_country=ES'

    def listing_url(self, offset):
        return self.url + f'&sortColumn=referencedate&sortDirection=desc&startrow={offset}'
