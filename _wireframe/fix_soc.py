import io

p = 'index.html'
ls = io.open(p, encoding='utf-8').read().split('\n')
out = []
for ln in ls:
    if 'Discord' in ln and 'aria-label' in ln:
        continue
    if 'aria-label=' in ln and ('YouTube' in ln or 'Telegram' in ln or 'TikTok' in ln):
        i = ln.find('</a>')
        if i != -1:
            ln = ln[:i + 4]
    out.append(ln)
io.open(p, 'w', encoding='utf-8').write('\n'.join(out))
print('ok')
