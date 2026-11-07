"""Exercise the pinned benchmark's actual request/loader/response interfaces; no benchmark score."""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from osa_eval.contracts import Reply,Usage,digest

ROOT=Path(os.environ.get('OSA_ASYNCODEBENCH_CHECKOUT',str(Path(__file__).resolve().parents[3]/'upstream/AsynCodeBench')))
RUNNER=ROOT/'reproductions/async-swe-agents'


@unittest.skipUnless((RUNNER/'agents/base.py').exists(),'Requires the pinned AsynCodeBench checkout')
class NativeContractTests(unittest.TestCase):
    def test_native_loader_passes_assigned_workspace_and_preserves_response_usage(self):
        sys.path.insert(0,str(RUNNER))
        try:
            from agents import AgentRunRequest,load_agent_adapter
            adapter_module=importlib.import_module('osa_eval.asyncodebench_adapter')
            commands=[]
            class Model:
                identity={'model':'fixture'}
                def __init__(self,*args,**kw):pass
                async def complete(self,messages,tools,*,role):
                    if messages[-1]['role']!='tool':
                        return Reply({'role':'assistant','content':None,'tool_calls':[{'id':'c','type':'function','function':{'name':'execute','arguments':json.dumps({'command':'git status --short'})}}]},Usage(20,10,.00003),'fixture')
                    return Reply({'role':'assistant','content':'Assignment complete'},Usage(25,5,.00003),'fixture')
            class Workspace:
                def execute_command(self,command,timeout):
                    commands.append(command)
                    return type('Result',(),{'stdout':'','stderr':'','exit_code':0})()
            with tempfile.TemporaryDirectory()as output,patch.object(adapter_module,'ChatModel',Model),patch.dict(os.environ,{'LLM_BASE_URL':'http://localhost/v1','LLM_API_KEY':'test-only'}):
                adapter=load_agent_adapter(agent_import_path='osa_eval.asyncodebench_adapter:SharedWorkerAdapter',agent_config_json={'input_usd_per_million':1,'output_usd_per_million':1,'request_token_reservation':1000})
                request=AgentRunRequest('0.1','asyncodebench:cachetools','commit0:cachetools','async_private','scenario','worker','assignment',1,'Implement assigned public scope','/private/worktree',('src/file.py',),('tests/test_file.py',),(), 'fixture',4,output,Workspace())
                response=adapter.execute(request)
                self.assertIsNone(response.error)
                self.assertEqual(response.prompt_tokens,45)
                self.assertEqual(response.completion_tokens,15)
                self.assertAlmostEqual(response.cost,.00006)
                self.assertEqual(commands,['cd /private/worktree && git status --short'])
                self.assertEqual(response.metadata['identity']['request_sha256'],digest(request.public_metadata()))
        finally:sys.path.remove(str(RUNNER))
