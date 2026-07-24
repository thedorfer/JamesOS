from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw
from jamesos.services.commerce_mockup_composer import MockupTemplateRegistry,TEMPLATE_ROOT

def create(template_id,category,pose,color,shirt_box,body=False):
    root=TEMPLATE_ROOT;root.mkdir(parents=True,exist_ok=True);base=Image.new("RGBA",(1200,1200),(232,229,222,255));draw=ImageDraw.Draw(base);mask=Image.new("L",base.size,0);shirt=ImageDraw.Draw(mask)
    if body:
        draw.ellipse((480,70,720,310),fill=(178,145,122,255));draw.rounded_rectangle((390,260,810,1120),70,fill=(120,115,110,255));draw.polygon([(390,340),(190,720),(360,790),(470,510)],fill=(178,145,122,255));draw.polygon([(810,340),(1010,720),(840,790),(730,510)],fill=(178,145,122,255))
    x0,y0,x1,y1=shirt_box;shirt.polygon([(x0+90,y0),(x1-90,y0),(x1,y0+170),(x1-80,y0+250),(x1-110,y1),(x0+110,y1),(x0+80,y0+250),(x0,y0+170)],fill=255)
    overlay=Image.new("RGBA",base.size,(0,0,0,0));overlay.paste(Image.new("RGBA",base.size,color),mask=mask);base=Image.alpha_composite(base,overlay)
    base_name=f"{template_id}-v1-base.png";mask_name=f"{template_id}-v1-mask.png";base.save(root/base_name);mask.save(root/mask_name)
    labels={"clean-black-shirt":("Clean shirt test placeholder","clean_product"),"male-black-shirt":("Male mannequin test placeholder","male_model"),"female-black-shirt":("Female mannequin test placeholder","female_model")};label,role=labels[template_id];inset=150;registry=MockupTemplateRegistry(root);registry.register({"template_id":template_id,"version":"1.0","display_name":label,"model_category":category,"subject_role":role,"template_kind":"placeholder","production_allowed":False,"pose":pose,"garment_style":"unisex crew-neck T-shirt","garment_color":"black","base_image":base_name,"shirt_mask":mask_name,"print_area":[[x0+inset,y0+210],[x1-inset,y0+210],[x1-inset-20,y1-150],[x0+inset+20,y1-150]],"provenance":{"source":"JamesOS deterministic procedural template","creator":"JamesOS deterministic bootstrap","license":"JamesOS test-only generated asset","created_at":"2026-07-19T00:00:00-05:00","notes":"Compositor verification placeholder; not marketplace eligible."}})

create("clean-black-shirt","product-only","flat front",(28,29,34,255),(250,130,950,1080),False)
create("male-black-shirt","male","standing front mannequin",(24,26,31,255),(330,270,870,1040),True)
create("female-black-shirt","female","standing front mannequin",(30,28,33,255),(350,260,850,1020),True)
print(TEMPLATE_ROOT)
