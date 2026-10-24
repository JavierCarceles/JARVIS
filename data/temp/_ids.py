import os,tempfile,sys,json
td=tempfile.mkdtemp()
sys.path.append('src')
from utils.contextual_adaptation_engine import ContextType, ContextualAdaptationEngine
e=ContextualAdaptationEngine(data_dir=td)
def fb(i):
    return {'adaptation_id':f'obs_{i}','original_goal_id':f'g{i}','adapted_goal_id':f'a{i}','adaptation_context':{'goal_type':'navigation','context_type':ContextType.PRODUCTION.value,'system_resources':{'cpu':0.5,'memory':0.3},'expected_metrics':{'response_time':2.0,'accuracy':0.95}},'execution_result':{'success':True,'performance_metrics':{'response_time':1.2,'accuracy':0.97}},'verification_result':{'verified':True,'impact_score':0.8}}
produced=[]
for i in range(1,4):
    fr=e._capture_goal_adaptation_feedback(fb(i))
    lr=e._execute_goal_adaptation_learning_loop(fr)
    produced.extend(p['pattern_id'] for p in lr['learned_patterns'])
path=os.path.join(td,'goal_adaptation_learning_results.json')
data=json.load(open(path))
disk=[p['pattern_id'] for row in data['learning_results'] for p in row['learned_patterns']]
open('data/temp/ids.txt','w',encoding='ascii').write('produced='+str(produced)+'\n'+'disk='+str(disk)+'\n')