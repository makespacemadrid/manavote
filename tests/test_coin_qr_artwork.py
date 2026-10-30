"""Branded labels must remain readable at the actual printed image size."""
import pytest
from PIL import Image
from app.services.coin_qr_service import render_coin_qr, qr_brand

@pytest.mark.parametrize('name,brand',[('Coke','coke'),(' coke ','coke'),('Coca-Cola','coke'),('Coke Zero','zero'),('coca-cola zero','zero'),('Other Can',None)])
def test_qr_brand_aliases(name,brand):
    assert qr_brand(name)==brand

@pytest.mark.parametrize('name',['Coke','Coke Zero','Other Can'])
@pytest.mark.parametrize('base',['https://vote.example','https://members.example.org/manavote/shared-space'])
def test_branded_qr_decodes_at_print_size(name,base):
    zxingcpp=pytest.importorskip('zxingcpp')
    url=base+'/koins/scan/'+'test-token-'+'a'*48
    image=render_coin_qr(url,name)
    for width in [image.width,280,220]:
        scaled=image.resize((width,width),Image.Resampling.LANCZOS)
        decoded=zxingcpp.read_barcode(scaled)
        assert decoded is not None and decoded.text==url
    # The quiet zone stays intact even with the embedded brand artwork.
    assert image.getpixel((0,0))==(255,255,255)
    if name=='Coke':
        center=image.crop((image.width//3,image.height//3,image.width*2//3,image.height*2//3))
        assert any(r>g*2 and r>b*2 for r,g,b in (center.getpixel((x,y)) for x in range(center.width) for y in range(center.height)))
