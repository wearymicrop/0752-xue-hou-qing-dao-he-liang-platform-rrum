def test_all_preview_sections_match_archive(client):
    run = client.post('/api/runs',json={'sample':'dirty'}).json()
    for name in ('routes','tracks','projection','windows','coverage','reconcile'):
        response = client.get(f'/api/{name}/dirty')
        assert response.status_code == 200 and response.json() == run['result'][name]


def test_clean_preview_and_home(client):
    response = client.get('/?sample=clean')
    assert response.status_code == 200 and '道路覆盖地图' in response.text
    assert client.get('/api/previews/clean').json()['reconcile']['totals']['covered_m'] == 5265


def test_invalid_sample_error(client):
    response = client.get('/api/coverage/typo')
    assert response.status_code == 404 and response.json()['code'] == 'UNKNOWN_SAMPLE'
