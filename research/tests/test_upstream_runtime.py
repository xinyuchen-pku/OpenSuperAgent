import asyncio
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from osa_eval.contracts import Event,Limits,Reply,Usage
from osa_eval.journal import Journal
from osa_eval.kernel import Kernel
from osa_eval.smoke import DiagnosticWorkspace,DiagnosticModel
from osa_eval.upstream_runtime import CoreClient,UpstreamRuntime

CHECKOUT=Path(os.environ.get('OSA_UPSTREAM_CHECKOUT',str(Path(__file__).resolve().parents[3]/'upstream/dsh-superagent-prototype')))
AVAILABLE=shutil.which('node')and(CHECKOUT/'src/core/engine.ts').exists()


class AdmissionModel(DiagnosticModel):
    async def complete(self,messages,tools,*,role):
        if tools[0]['function']['name']=='decide':
            return Reply({'role':'assistant','content':None,'tool_calls':[{'id':'admit','type':'function','function':{
                'name':'decide','arguments':json.dumps({'kind':'accept','title':'Task','scope':'Public benchmark task','reason':'Explicit request'})}}]},Usage(30,10),'diagnostic','tool_calls')
        return await super().complete(messages,tools,role=role)


@unittest.skipUnless(AVAILABLE,'Requires Node 24 and the pinned upstream checkout')
class UpstreamTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.limits=Limits(token_budget=100_000,request_token_reservation=1000,tool_timeout_s=2,task_timeout_s=5)
        self.journal=Journal(self.root/'run.db',token_budget=100_000,identity={'purpose':'upstream contract'})

    async def asyncTearDown(self):self.temp.cleanup()

    async def test_actual_core_model_ports_and_restart_resume_keep_one_ticket(self):
        c=await CoreClient(CHECKOUT,self.root/'core.json').start()
        try:
            first=await asyncio.wait_for(UpstreamRuntime(c,Kernel(AdmissionModel(),self.journal,self.limits)).run(
                [Event('a','thread','Do task A')],{'a':DiagnosticWorkspace()}),10)
        finally:await c.close()
        self.assertEqual(len(first['tickets']),1)
        with self.journal.db()as db:
            requests=[json.loads(row[0]) for row in db.execute("SELECT payload FROM trace WHERE kind='model_request'")]
        worker=next(row for row in requests if row['role']=='worker')
        self.assertEqual(json.dumps(worker['messages']).count('Do task A'),1)
        ticket=first['tickets'][0]['id']
        c=await CoreClient(CHECKOUT,self.root/'core.json').start()
        try:
            second=await asyncio.wait_for(UpstreamRuntime(c,Kernel(AdmissionModel(),self.journal,self.limits)).run(
                [Event('b','thread','Check in-scope update',task_id='a',kind='followup')],{'a':DiagnosticWorkspace()}),10)
        finally:await c.close()
        self.assertEqual(len(second['tickets']),1)
        self.assertEqual(second['tickets'][0]['id'],ticket)
        self.assertEqual(len([x for x in self.journal.usage()['calls']if x['role']=='router']),1)
        self.assertEqual(len([x for x in self.journal.usage()['calls']if x['role']=='worker']),2)
        self.assertTrue(self.journal.usage()['accounting_valid'])


if __name__=='__main__':unittest.main()
