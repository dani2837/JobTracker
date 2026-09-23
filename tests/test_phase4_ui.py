from PySide6.QtCore import Qt
from app.services.source_configuration import configure_sources, GUADALTEL_URL
from app.database.repositories import CompanyRepository
from app.ui.spontaneous_application import SpontaneousApplicationPanel
from tests.test_ui import application, window


def test_guadaltel_panel_records_only_manual_actions(window,monkeypatch):
    configure_sources(window.db)
    repo=CompanyRepository(window.db)
    company=next(c for c in repo.get_companies() if c['name']=='Guadaltel')
    panel=SpontaneousApplicationPanel(repo,company,window)
    urls=[]
    monkeypatch.setattr('app.ui.common.QDesktopServices.openUrl',lambda url:urls.append(url.toString()) or True)
    monkeypatch.setattr('httpx.Client.request',lambda *a,**k: (_ for _ in ()).throw(AssertionError('No enviar formulario')))
    panel.status.setCurrentText('CV enviado')
    panel.notes.setPlainText('Registro manual de prueba')
    panel.save_button.click()
    assert panel.date.text()!='No enviada'
    saved=next(c for c in repo.get_companies() if c['name']=='Guadaltel')
    assert saved['spontaneous_application_status']=='CV enviado' and saved['notes']=='Registro manual de prueba'
    panel.open_button.click()
    assert urls==[GUADALTEL_URL]
    panel.close()


def test_source_filters_and_multisource_summary(window):
    view=window.jobs
    assert {'Sopra Steria','Izertis','Indra / Minsait','Deloitte'} <= {view.source_filter.itemText(i) for i in range(view.source_filter.count())}
    view.source_filter.setCurrentText('Izertis')
    assert view.table.rowCount()==0
    result={'total_found':10,'new_jobs':2,'updated_jobs':3,'excluded_jobs':5,'excluded':4,'errors':1,
        'sources':[{'source':'Izertis','success':True,'new_jobs':2,'updated_jobs':3,'excluded_jobs':5,'compatible':1},
                   {'source':'Deloitte','success':False,'error':'HTTP 503'}]}
    window.update_succeeded(result)
    assert 'Izertis' in view.update_status.toolTip() and 'Deloitte' in view.update_status.toolTip()
    assert 'HTTP 503' in view.update_status.toolTip() and '1 errores' in view.update_status.text()
