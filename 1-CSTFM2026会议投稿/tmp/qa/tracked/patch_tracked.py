from pathlib import Path
from zipfile import ZipFile
from lxml import etree as E
from copy import deepcopy
from datetime import datetime, timezone
import shutil, hashlib
base=Path('/Users/liangwang/345-亦庄交通仿真/1-CSTFM2026会议投稿')
src=base/'2-宣讲后修改/CT007-Clean.docx'
backup=base/'2-宣讲后修改/CT007-Clean_修订前备份.docx'
if backup.exists():
 assert backup.read_bytes()==src.read_bytes(),'Existing backup differs; abort.'
else: shutil.copy2(src,backup)
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main';R='http://schemas.openxmlformats.org/officeDocument/2006/relationships';P='http://schemas.openxmlformats.org/package/2006/relationships'
ns={'w':W,'a':'http://schemas.openxmlformats.org/drawingml/2006/main','wp':'http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing','pic':'http://schemas.openxmlformats.org/drawingml/2006/picture'}
qn=lambda n:'{'+W+'}'+n
now=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
with ZipFile(src) as z:
 infos=z.infolist();data={x.filename:z.read(x) for x in infos}
original=E.fromstring(data['word/document.xml']);doc=deepcopy(original)
assert not doc.xpath('.//w:ins|.//w:del',namespaces=ns)
ids=[int(x) for x in doc.xpath('//@w:id',namespaces=ns) if x.isdigit()];rid=max(ids+[100])+1
comments=E.Element(qn('comments'),nsmap={'w':W})
def rev(tag,run):
 global rid
 e=E.Element(qn(tag));e.set(qn('id'),str(rid));rid+=1;e.set(qn('author'),'Codex');e.set(qn('date'),now);e.append(run);return e
def comment(p,first,last,cid,text):
 start=E.Element(qn('commentRangeStart'));start.set(qn('id'),str(cid));p.insert(p.index(first),start)
 end=E.Element(qn('commentRangeEnd'));end.set(qn('id'),str(cid));p.insert(p.index(last)+1,end)
 ref=E.Element(qn('r'));rp=E.SubElement(ref,qn('rPr'));sty=E.SubElement(rp,qn('rStyle'));sty.set(qn('val'),'CommentReference');cr=E.SubElement(ref,qn('commentReference'));cr.set(qn('id'),str(cid));p.insert(p.index(end)+1,ref)
 c=E.SubElement(comments,qn('comment'));c.set(qn('id'),str(cid));c.set(qn('author'),'Codex');c.set(qn('initials'),'CX');c.set(qn('date'),now)
 cp=E.SubElement(c,qn('p'));rr=E.SubElement(cp,qn('r'));tt=E.SubElement(rr,qn('t'));tt.text=text
ps=doc.findall('w:body/w:p',ns)
p=next(p for p in ps if ''.join(p.xpath('.//w:t/text()',namespaces=ns)).startswith('We adopt a three-layer'))
run=p.find('w:r',ns);t=run.find('w:t',ns);assert t.text.startswith('We adopt')
old=deepcopy(run);old_t=old.find('w:t',ns);old_t.tag=qn('delText');old_t.text='We'
new=deepcopy(run);new.find('w:t',ns).text='As shown in Fig. 2, we'
t.text=t.text[2:];t.set('{http://www.w3.org/XML/1998/namespace}space','preserve')
delnode=rev('del',old);insnode=rev('ins',new);idx=p.index(run);p.insert(idx,delnode);p.insert(idx+1,insnode)
comment(p,delnode,insnode,0,'终审意见第2项：在第2.3节首句增加“As shown in Fig. 2”，明确引用图2。正文其余内容及字体、段落格式保持不变。')
p=next(p for p in ps if p.xpath('.//a:blip[@r:embed="rId8"]',namespaces={**ns,'r':R}))
old_run=next(x for x in p.findall('w:r',ns) if x.find('w:drawing',ns) is not None)
new_run=deepcopy(old_run)
new_run.find('.//a:blip',ns).set('{'+R+'}embed','rIdFig2Revision')
max_docpr=max([int(x.get('id')) for x in doc.findall('.//wp:docPr',ns)]+[0])+1
new_run.find('.//wp:docPr',ns).set('id',str(max_docpr));new_run.find('.//wp:docPr',ns).set('name','Fig. 2 revised technical roadmap')
new_run.find('.//pic:cNvPr',ns).set('id',str(max_docpr))
pos=p.index(old_run);p.remove(old_run);deleted=rev('del',old_run);inserted=rev('ins',new_run);p.insert(pos,deleted);p.insert(pos+1,inserted)
comment(p,deleted,inserted,1,'终审意见第3项：将低清晰度、跨软件可能空白的原EMF图替换为4800×1688像素高清图，保持原图宽高和位置。按第2.3节重绘三层框架；原图含物资完成率100%、疏散率9.1%等旧版结果，故移除这些与当前正文不一致的结果数字。可通过“接受/拒绝”逐项审阅图件替换。')
settings=E.fromstring(data['word/settings.xml'])
for tag in ('revisionView','trackRevisions'):
 existing=settings.find('w:'+tag,ns)
 if existing is not None:settings.remove(existing)
rv=E.Element(qn('revisionView'));rv.set(qn('markup'),'1');rv.set(qn('comments'),'1');rv.set(qn('insDel'),'1');rv.set(qn('formatting'),'0')
tr=E.Element(qn('trackRevisions'));tr.set(qn('val'),'1')
# CT_Settings places revision display/tracking before document protection/defaultTabStop.
anchor=next((x for x in settings if E.QName(x).localname in ('documentProtection','autoFormatOverride','styleLockTheme','styleLockQFSet','defaultTabStop','autoHyphenation')),None)
i=settings.index(anchor) if anchor is not None else 0;settings.insert(i,rv);settings.insert(i+1,tr)
rels=E.fromstring(data['word/_rels/document.xml.rels'])
for id,typ,target in [('rIdFig2Revision','image','media/figure2_highres.png'),('rIdRevisionComments','comments','comments.xml')]:
 e=E.SubElement(rels,'{'+P+'}Relationship');e.set('Id',id);e.set('Type',R+'/'+typ);e.set('Target',target)
ct=E.fromstring(data['[Content_Types].xml']);e=E.SubElement(ct,'{http://schemas.openxmlformats.org/package/2006/content-types}Override');e.set('PartName','/word/comments.xml');e.set('ContentType','application/vnd.openxmlformats-officedocument.wordprocessingml.comments+xml')
def xml(r):return E.tostring(r,xml_declaration=True,encoding='UTF-8',standalone=True)
for key,r in [('word/document.xml',doc),('word/settings.xml',settings),('word/_rels/document.xml.rels',rels),('[Content_Types].xml',ct),('word/comments.xml',comments)]:data[key]=xml(r)
data['word/media/figure2_highres.png']=(base/'2-宣讲后修改/终审修订/Fig2_technical_roadmap.png').read_bytes()
def write(path,parts):
 with ZipFile(path,'w') as z:
  for inf in infos:z.writestr(inf,parts[inf.filename])
  for n,b in parts.items():
   if n not in [i.filename for i in infos]:z.writestr(n,b)
# Verify that rejection restores original visible text and image references.
for mode in ('accepted','rejected'):
 r=deepcopy(doc)
 for tag,keep in [('ins',mode=='accepted'),('del',mode=='rejected')]:
  for node in r.findall('.//w:'+tag,ns):
   parent=node.getparent();i=parent.index(node)
   if keep:
    for ch in list(node):
     for dt in ch.findall('.//w:delText',ns):dt.tag=qn('t')
     parent.insert(i,ch);i+=1
   parent.remove(node)
 for node in r.xpath('.//w:commentRangeStart|.//w:commentRangeEnd|.//w:commentReference',namespaces=ns):node.getparent().remove(node)
 if mode=='rejected':
  assert r.xpath('.//w:t/text()',namespaces=ns)!=[]
  assert ''.join(r.xpath('.//w:t/text()',namespaces=ns))==''.join(original.xpath('.//w:t/text()',namespaces=ns))
  assert r.xpath('.//a:blip/@r:embed',namespaces={**ns,'r':R})==original.xpath('.//a:blip/@r:embed',namespaces={**ns,'r':R})
 for xp in ('.//w:pPr','.//w:sectPr','.//w:tblPr'):
  assert [E.tostring(x) for x in r.xpath(xp,namespaces=ns)]==[E.tostring(x) for x in original.xpath(xp,namespaces=ns)]
 parts=dict(data);parts['word/document.xml']=xml(r);write(base/f'tmp/qa/tracked/{mode}.docx',parts)
# Write atomically over the explicitly requested original path.
staged=src.with_suffix('.tracked-tmp.docx');write(staged,data);staged.replace(src)
print('Updated:',src);print('Backup:',backup)
print('Tracked insertions:',len(doc.findall('.//w:ins',ns)),'deletions:',len(doc.findall('.//w:del',ns)),'comments:',len(comments))
print('Reject all restores original text and image references; all paragraph/section/table properties preserved.')
