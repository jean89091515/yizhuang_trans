from pathlib import Path
from zipfile import ZipFile
from lxml import etree
from html import escape
import json
root=Path('/Users/liangwang/345-亦庄交通仿真/1-CSTFM2026会议投稿')
out=root/'2-宣讲后修改/终审修订'
svg=['<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="422" viewBox="0 0 1200 422">', '<rect width="1200" height="422" fill="white"/>','<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#333333"/></marker></defs>']
cols=[(2,'1  Scenario construction','#23547a',[
 ('Data integration',True),('Roads · facilities · population',False),('OD flows · age structure',False),
 ('Dispersion and disruption',True),('Gaussian plume → ERPG zones',False),('Road closures · congestion',False),
 ('Shared scenario inputs',True),('Network · evacuation demand',False),('Shelter-in-place supply demand',False)]),
 (416,'2  Coordinated optimization','#296044',[
 ('Supply distribution',True),('Truck–drone · four priorities',False),('Time windows · greedy + 2-opt',False),
 ('Multimodal evacuation',True),('Five modes · three vulnerability',False),('classes · risk-aware dispatch',False),
 ('Supply–evacuation coupling',True),('Shared network · resources',False),('Timing · opposing travel flows',False)]),
 (830,'3  Resilience assessment','#734835',[
 ('Structural resilience',True),('Closure length and ratio',False),
 ('Functional resilience',True),('Supply / evacuation completion',False),('On-time rescue · risk exposure',False),
 ('Adaptive resilience',True),('Relay / fleet interventions',False),
 ('Decision support',True),('Fleet sizing · pre-positioning',False)])]
# Final physical width is unchanged (4.575 inches); 25 px is about 6.9 pt.
for x,title,color,lines in cols:
 svg.append(f'<rect x="{x}" y="2" width="368" height="418" rx="6" fill="#ffffff" stroke="{color}" stroke-width="2"/>')
 svg.append(f'<rect x="{x+1}" y="3" width="366" height="47" rx="5" fill="{color}"/>')
 svg.append(f'<text x="{x+184}" y="34" text-anchor="middle" font-family="Times New Roman" font-size="27" font-weight="bold" fill="white">{escape(title)}</text>')
 for i,(t,bold) in enumerate(lines):
  y=86+i*36
  svg.append(f'<text x="{x+14}" y="{y}" font-family="Times New Roman" font-size="25" font-weight="{"bold" if bold else "normal"}" fill="{color if bold else "#111111"}">{escape(t)}</text>')
for x in (376,790):
 svg.append(f'<path d="M{x},211 H{x+30}" fill="none" stroke="#333333" stroke-width="2.5" marker-end="url(#arrow)"/>')
svg.append('</svg>')
(out/'Fig2_technical_roadmap.svg').write_text('\n'.join(svg))
