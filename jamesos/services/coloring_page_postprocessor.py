"""Shared deterministic postprocessing and validation for coloring-page assets."""
from __future__ import annotations
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image,ImageEnhance,ImageFilter,ImageOps

from jamesos.core.artifacts import AtomicDocumentStore,now


DEFAULT_PARAMETERS={"threshold":205,"median_filter_size":3,"contour_filter_size":3,"edge_margin_pixels":16}
DEFAULT_THRESHOLDS={"minimum_white_ratio":0.72,"minimum_dark_pixel_ratio":0.004,"maximum_dark_pixel_ratio":0.28,"maximum_largest_black_component_ratio":0.12,"maximum_edge_dark_ratio":0.0,"maximum_grayscale_ratio":0.18}


def _largest_component_ratio(image:Image.Image)->float:
    width,height=image.size;black={(x,y) for y in range(height) for x in range(width) if image.getpixel((x,y))==0};largest=0
    while black:
        stack=[black.pop()];size=0
        while stack:
            x,y=stack.pop();size+=1
            for point in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if point in black:black.remove(point);stack.append(point)
        largest=max(largest,size)
    return largest/max(1,width*height)


def process_coloring_page(content:bytes,raw_path:Path,processed_path:Path,*,profile_id:str,workflow_hash:str,expected_width:int,expected_height:int,parameters:dict[str,Any]|None=None,thresholds:dict[str,Any]|None=None)->dict[str,Any]:
    params={**DEFAULT_PARAMETERS,**(parameters or {})};limits={**DEFAULT_THRESHOLDS,**(thresholds or {})}
    raw_path.parent.mkdir(parents=True,exist_ok=True);processed_path.parent.mkdir(parents=True,exist_ok=True);raw_path.write_bytes(content)
    with Image.open(BytesIO(content)) as source:
        source.load();source_format=source.format;source_gray=source.convert("L");raw_pixels=list(source_gray.getdata());grayscale=sum(16<x<240 for x in raw_pixels)/max(1,len(raw_pixels));gray=ImageOps.autocontrast(source_gray)
        hard=params.get("hard_binary_threshold",True) is not False
        if hard:binary=gray.point(lambda value:255 if value>=int(params["threshold"]) else 0,"1").convert("L")
        else:
            binary=ImageEnhance.Contrast(gray).enhance(float(params.get("contrast_increase") or 1.12));binary=binary.point(lambda value:255 if value>=int(params.get("background_white_point") or 232) else value)
        margin=int(params["edge_margin_pixels"]);width,height=binary.size
        raw_edge=list(binary.crop((0,0,width,margin)).getdata())+list(binary.crop((0,height-margin,width,height)).getdata())+list(binary.crop((0,0,margin,height)).getdata())+list(binary.crop((width-margin,0,width,height)).getdata());raw_edge_dark=sum(x<=80 for x in raw_edge)/max(1,len(raw_edge));canvas_padding_applied=False
        if params.get("white_canvas_padding_on_margin_failure") and raw_edge_dark>float(limits["maximum_edge_dark_ratio"]):
            padding=max(margin,int(params.get("canvas_padding_pixels") or margin));inner_width=max(1,width-padding*2);inner_height=max(1,height-padding*2);fitted=ImageOps.contain(binary,(inner_width,inner_height),Image.Resampling.LANCZOS);canvas=Image.new("L",(width,height),255);canvas.paste(fitted,((width-fitted.width)//2,(height-fitted.height)//2));binary=canvas;raw_edge_dark=0.0;canvas_padding_applied=True
        binary=binary.filter(ImageFilter.MedianFilter(int(params["median_filter_size"])))
        if hard and int(params.get("contour_filter_size") or 1)>1:binary=binary.filter(ImageFilter.MinFilter(int(params["contour_filter_size"])))
        pixels=binary.load()
        for y in range(height):
            for x in range(width):
                if x<margin or y<margin or x>=width-margin or y>=height-margin:pixels[x,y]=255
        output=BytesIO();binary.save(output,"PNG");processed=output.getvalue();processed_path.write_bytes(processed)
    values=list(binary.getdata());total=max(1,len(values));white=sum(x>=240 for x in values)/total;dark=sum(x<=80 for x in values)/total
    edge=list(binary.crop((0,0,width,margin)).getdata())+list(binary.crop((0,height-margin,width,height)).getdata())+list(binary.crop((0,0,margin,height)).getdata())+list(binary.crop((width-margin,0,width,height)).getdata());edge_dark=sum(x<=80 for x in edge)/max(1,len(edge));component_mask=binary.point(lambda value:0 if value<=80 else 255);largest=_largest_component_ratio(component_mask)
    checks={"dimensions":(width,height)==(expected_width,expected_height),"mostly_white_background":white>=float(limits["minimum_white_ratio"]),"not_blank":dark>=float(limits["minimum_dark_pixel_ratio"]),"dark_pixel_ratio":dark<=float(limits["maximum_dark_pixel_ratio"]),"largest_black_component":largest<=float(limits["maximum_largest_black_component_ratio"]),"safe_margins":raw_edge_dark<=float(limits["maximum_edge_dark_ratio"]),"excessive_grayscale":grayscale<=float(limits["maximum_grayscale_ratio"])}
    reasons=[name.replace("_"," ") for name,passed in checks.items() if not passed]
    validation={"valid":not reasons,"failed_reasons":reasons,"dimensions_valid":checks["dimensions"],"format":source_format,"processed_format":"PNG","mostly_white_background":checks["mostly_white_background"],"white_ratio":round(white,4),"dark_pixel_ratio":round(dark,4),"black_line_coverage":round(dark,4),"largest_solid_black_component_ratio":round(largest,4),"edge_dark_ratio":round(edge_dark,4),"raw_edge_dark_ratio":round(raw_edge_dark,4),"grayscale_ratio":round(grayscale,4),"not_blank":checks["not_blank"],"safe_margins":checks["safe_margins"],"processed_image_valid":not reasons}
    metadata={"profile_id":profile_id,"workflow_hash":workflow_hash,"raw_file_sha256":sha256(content).hexdigest(),"processed_file_sha256":sha256(processed).hexdigest(),"processing_parameters":params,"canvas_padding_applied":canvas_padding_applied,"semantic_content_modified":False,"validation_thresholds":limits,"processed_at":now(),"technical_validation":validation}
    AtomicDocumentStore().write_json(processed_path.with_suffix(".processing.json"),metadata)
    return {**metadata,"width":width,"height":height,"processed_content":processed}
