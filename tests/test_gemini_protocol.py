"""ネットワークを使わず、公式Interactions APIの呼出形式をモックする試験。"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from robot_agent import GeminiCalls, check_sdk_compatibility

class FakeInteractions:
    def __init__(self, replies): self.replies=list(replies);self.calls=[]
    def create(self,**kw):
        self.calls.append(kw)
        return self.replies.pop(0)

def mkcall(i,name,args,cid):
    return SimpleNamespace(id=i,steps=[SimpleNamespace(type='function_call',name=name,arguments=args,id=cid)],output_text='')

def mktext(i,value):
    return SimpleNamespace(id=i,steps=[],output_text=value)

class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.fake=FakeInteractions([
            mkcall('r1','start_navigation',{'destination':'SHELF_A'},'c1'),
            mkcall('r2','start_navigation',{'destination':'SHELF_B'},'c2'),
            mktext('r3','棚Bへの移動を完了しました')])
        self.agent=GeminiCalls.__new__(GeminiCalls)
        self.agent.client=SimpleNamespace(interactions=self.fake)
        self.agent.model='gemini-robotics-er-2-preview'
        self.agent.interaction=None
    def test_function_result_carries_previous_interaction_id(self):
        self.agent.begin('棚Aへ',{'version':1,'SHELF_A':'available','SHELF_B':'available'})
        name,args,cid=self.agent.next_after_result('start_navigation','c1',{'status':'CANCELED_OR_TERMINATED','world':{'version':2,'SHELF_A':'blocked','SHELF_B':'available'}},expect_tool=True)
        self.assertEqual((name,args['destination'],cid),('start_navigation','SHELF_B','c2'))
        self.assertEqual(self.fake.calls[1]['previous_interaction_id'],'r1')
        self.assertEqual(self.fake.calls[1]['input'][0]['call_id'],'c1')
        self.assertEqual(self.fake.calls[1]['input'][0]['type'],'function_result')
        self.assertEqual(self.agent.next_after_result('start_navigation','c2',{'status':'SUCCEEDED'},expect_tool=False),'棚Bへの移動を完了しました')
        self.assertEqual(self.fake.calls[2]['previous_interaction_id'],'r2')
    def test_sdk_version_gate(self):
        self.assertTrue(check_sdk_compatibility('2.33.0'))
        self.assertTrue(check_sdk_compatibility('3.0.0'))
        self.assertFalse(check_sdk_compatibility('1.75.0'))
        self.assertFalse(check_sdk_compatibility('unknown'))

    def test_multiple_function_calls_rejected(self):
        self.fake=FakeInteractions([SimpleNamespace(
            id='r1',steps=[
                SimpleNamespace(type='function_call',name='start_navigation',arguments={'destination':'SHELF_A'},id='c1'),
                SimpleNamespace(type='function_call',name='start_navigation',arguments={'destination':'SHELF_B'},id='c2')],output_text='')])
        self.agent.client=SimpleNamespace(interactions=self.fake)
        with self.assertRaisesRegex(RuntimeError, '1件必須'):
            self.agent.begin('棚Aへ',{'version':1,'SHELF_A':'available','SHELF_B':'available'})

    def test_initial_prompt_mentions_natural_language_task(self):
        self.agent.begin('棚Aへ移動してください',{'version':1,'SHELF_A':'available','SHELF_B':'available'})
        payload=self.fake.calls[0]
        self.assertEqual(payload['tools'][0]['name'],'start_navigation')
        self.assertEqual(payload['tools'][1]['name'],'stop_task')
        self.assertIn('棚Aへ移動してください',payload['input'][0]['content'][0]['text'])

if __name__=='__main__':unittest.main()
