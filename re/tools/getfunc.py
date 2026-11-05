import re,sys
src=open(sys.argv[1]).read()
want=[int(x,16) for x in sys.argv[2:]]
for part in re.split(r'^//@@FUNC ',src,flags=re.M)[1:]:
    hdr,body=part.split('\n',1)
    if int(hdr.split()[0],16) in want: print('//@@',hdr); print(body)
