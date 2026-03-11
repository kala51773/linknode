import os

def update_file(path):
    with open(path, 'r', encoding='utf-8') as f:
        content = f.read()

    new_content = content.replace('"u": 101,', '"u": 101, "pu": 100,')
    new_content = new_content.replace('"u":101,', '"u":101,"pu":100,')
    new_content = new_content.replace('"u": 102,', '"u": 102, "pu": 101,')
    new_content = new_content.replace('"u":102,', '"u":102,"pu":101,')

    if new_content != content:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(new_content)

for r, d, f in os.walk('tests'):
    for file in f:
        if file.endswith('.py'):
            update_file(os.path.join(r, file))

for r, d, f in os.walk('src'):
    for file in f:
        if file.endswith('.py'):
            update_file(os.path.join(r, file))
