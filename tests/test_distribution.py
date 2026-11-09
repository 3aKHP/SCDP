import threading
import httpx
from scdp.distribution import server


def test_private_download_and_range(tmp_path):
    token=tmp_path/'auth.token';token.write_text('synthetic-admin\nsynthetic-user\n')
    releases=tmp_path/'releases';releases.mkdir()
    name='a'*64+'.tar.gz';(releases/name).write_bytes(b'fictional-package')
    http=server(releases,token,port=0)
    thread=threading.Thread(target=http.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{http.server_port}'
    try:
        with httpx.Client() as client:
            assert client.get(url+'/'+name).status_code==401
            assert client.get(url+'/'+name,headers={'Authorization':'Bearer synthetic-user'}).status_code==401
            headers={'Authorization':'Bearer synthetic-admin'}
            assert client.get(url+'/'+name,headers=headers).content==b'fictional-package'
            ranged=client.get(url+'/'+name,headers={**headers,'Range':'bytes=2-6'})
            assert ranged.status_code==206 and ranged.content==b'ction'
            assert client.get(url+'/invalid.tar.gz',headers=headers).status_code==404
            assert client.get(url+'/'+name,headers={**headers,'Range':'bytes=100-'}).status_code==416
    finally:
        http.shutdown();thread.join();http.server_close()
