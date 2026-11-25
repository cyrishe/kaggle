"""Render a replayed arithmetic DAG with true dependency depth as horizontal position."""
from collections import defaultdict
import json
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def render(ident, nodes, path):
    by_id={n['step']:n for n in nodes}
    layers=defaultdict(list)
    for n in nodes:
        layers[n['depth']].append(n)
    critical=set()
    current=max(nodes, key=lambda n:(n['depth'],bool(n.get('first'))))
    while True:
        critical.add(current['step'])
        if not current.get('operands'):break
        current=max((by_id[i] for i in current['operands']),key=lambda n:n['depth'])
    width=225*(1+max(layers))+30
    height=90*max(map(len,layers.values()))+160
    svg=ET.Element('svg',xmlns='http://www.w3.org/2000/svg',width=str(width),height=str(height),
                   viewBox=f'0 0 {width} {height}')
    def elem(tag,**attrs):
        return ET.SubElement(svg,tag,{k:str(v) for k,v in attrs.items()})
    def label(x,y,content,size=13,color='#182838'):
        elem('text',x=x,y=y,fill=color,**{'font-size':size,'font-family':'sans-serif'}).text=content
    elem('rect',width=width,height=height,fill='#fcfcfa')
    label(20,32,f'{ident}   ·   {len([n for n in nodes if n["step"]>0])} 步   ·   最大 {max(layers)} 阶',23)
    label(20,60,'从左到右依次升阶。★ 表示正式目标，紫线标出一条最长依赖链。每个节点列出两项操作数的来源。')
    pos={}
    for depth,group in sorted(layers.items()):
        for j,n in enumerate(group):
            pos[n['step']]=(20+225*depth,110+j*90)
        label(20+225*depth,93,f'{depth} 阶',14)
    edges=[]
    for n in nodes:
        for i in sorted(set(n.get('operands',[]))):
            primary=i in critical and n['step'] in critical and by_id[i]['depth']+1==n['depth']
            edges.append((primary,i,n['step']))
    for primary,i,j in sorted(edges):
        x,y=pos[i];xx,yy=pos[j]; x+=183; y+=28; yy+=28
        elem('path',d=f'M{x},{y} C{x+26},{y} {xx-26},{yy} {xx},{yy}',fill='none',
             stroke='#6c44a2' if primary else '#92a1ab',**{'stroke-width':2.5 if primary else 1,'opacity':1 if primary else .55})
    def ref(i):
        return f'#{i}' if i>0 else f'r{by_id[i]["register"]}'
    for n in nodes:
        i=n['step'];x,y=pos[i]
        elem('rect',x=x,y=y,width=183,height=60,rx=5,
             fill='#fff1ce' if n.get('target') else '#f2f5f6',stroke='#80629b' if i in critical else '#82939c')
        label(x+7,y+16,ref(i)+('  ★' if n.get('target') else ''),12)
        label(x+7,y+34,str(n['value']),15)
        operands=n.get('operands')
        desc=(f'{ref(operands[0])} {n["op"]} {ref(operands[1])}' if operands else '初始寄存器')
        label(x+7,y+51,desc,12)
    ET.ElementTree(svg).write(path,encoding='utf-8',xml_declaration=True)
    ET.parse(path)


if __name__=='__main__':
    reports=ROOT/'reports'
    study=json.loads((reports/'depth_graph_study.json').read_text())
    for ident in ('scored_0051','scored_0253'):
        render(ident,study['graphs'][ident],reports/f'{ident}_depth.svg')
