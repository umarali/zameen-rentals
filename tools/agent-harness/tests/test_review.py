import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('harness_review', Path(__file__).resolve().parents[1] / 'review.py')
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def result(model=review.MODEL, verdict='PASS', findings=None):
    return {'is_error': False, 'subtype': 'success',
            'modelUsage': {model: {'canonicalModel': model}},
            'result': json.dumps({'verdict': verdict, 'material_findings': findings or [], 'scope': 'Supplied snapshot only.'})}


class ReviewGateTests(unittest.TestCase):
    def test_accepts_only_exact_model_and_unqualified_pass(self):
        self.assertEqual(review.validate_result(result())['verdict'], 'PASS')
        for data in [result('claude-opus-other'), result(verdict='CHANGES_NEEDED'),
                     result(findings=['Broken contract']), {**result(), 'is_error': True},
                     {**result(), 'modelUsage': {}}, {**result(), 'result': 'PASS'}]:
            with self.subTest(data=data), self.assertRaises(ValueError):
                review.validate_result(data)

    def test_detects_file_edits_and_mode_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); path = root / 'candidate.py'; path.write_text('before')
            files = review.snapshot(root, ['candidate.py'])
            review.assert_unchanged(root, files)
            path.write_text('after')
            with self.assertRaises(ValueError): review.assert_unchanged(root, files)
            path.write_text('before'); path.chmod(0o700)
            with self.assertRaises(ValueError): review.assert_unchanged(root, files)

    def test_rejects_paths_outside_root_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve(); (root / 'real').write_text('data'); (root / 'link').symlink_to(root / 'real')
            for name in ['../outside', '/etc/hosts', 'link', 'missing']:
                with self.subTest(name=name), self.assertRaises(ValueError): review.snapshot(root, [name])

    def test_check_rejects_modified_packet(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); (root / 'candidate').write_text('x')
            (root / 'result.json').write_text(json.dumps(result())); (root / 'packet.txt').write_text('original')
            receipt={'verdict':'PASS','requested_effort':'high','files':review.snapshot(root,['candidate']),
                     'result_sha256':review.digest((root/'result.json').read_bytes()),'packet_sha256':review.digest(b'original')}
            (root/'candidate.json').write_text(json.dumps(receipt['files']))
            (root/'invocation.json').write_text(json.dumps({'requested_model':review.MODEL,'requested_effort':'high'}))
            for name in ['candidate','invocation']:
                receipt[name+'_sha256']=review.digest((root/(name+'.json')).read_bytes())
            (root/'receipt.json').write_text(json.dumps(receipt))
            args=type('Args',(),{'root':root,'receipt':root/'receipt.json'})()
            review.check(args)
            (root/'packet.txt').write_text('changed')
            with self.assertRaises(ValueError): review.check(args)

    def test_auth_failure_never_calls_model(self):
        with tempfile.TemporaryDirectory() as directory:
            base=Path(directory); root=base/'repo'; root.mkdir(); (root/'a').write_text('x'); context=base/'context'; context.write_text('test')
            args=type('Args',(),{'root':root,'output':base/'review','files':['a'],'context':context,'claude':'claude','timeout':1})()
            response=type('Result',(),{'returncode':1,'stdout':'{"loggedIn": false}'})()
            with patch.object(review.subprocess,'run',return_value=response) as run:
                with self.assertRaises(ValueError): review.review(args)
                self.assertEqual(run.call_count,1)


if __name__=='__main__': unittest.main()
