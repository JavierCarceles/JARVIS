with open(r'c:\Informatica\PROYECTOS\BACKEND/IA_PYTHON\IA/JARVIS/README.md', encoding='utf-8') as f:
    content = f.read()

# Search for __iter__
idx = content.find('__iter__')
if idx >= 0:
    print('Found __iter__ at index', idx)
    print('Context:', repr(content[idx-30:idx+50]))
else:
    print('__iter__ NOT FOUND in README')

# Search for the feedback/learning section
idx2 = content.find('Metodos de feedback y aprendizaje')
if idx2 >= 0:
    print('\nFound section at index', idx2)
    print('Content:', repr(content[idx2:idx2+500]))
else:
    print('Section NOT FOUND')

# Search for __getattr__
idx3 = content.find('__getattr__')
if idx3 >= 0:
    print('\nFound __getattr__ at index', idx3)
    print('Context:', repr(content[idx3-30:idx3+80]))
else:
    print('__getattr__ NOT FOUND')
