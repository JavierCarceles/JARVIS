import re

content = open('test_cross_context_confidence_feedback.py', 'r', encoding='utf-8').read()

# Reemplazos
content = content.replace('transfer_id="test_transfer_3"', 'transfer_id="test_transfer_3", knowledge_data={}')
content = content.replace('transfer_id="test_transfer_10"', 'transfer_id="test_transfer_10", knowledge_data={}')
content = content.replace('transfer_id="test_transfer_11"', 'transfer_id="test_transfer_11", knowledge_data={}')
content = content.replace('transfer_id="test_transfer_12"', 'transfer_id="test_transfer_12", knowledge_data={}')
content = content.replace(', confidence_score=', ', ')

open('test_cross_context_confidence_feedback.py', 'w', encoding='utf-8').write(content)
print('Fixed')
