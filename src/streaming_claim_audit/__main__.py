"""Command-line interface; audited code is never imported or executed."""
import argparse
import json
import sys
from . import __version__
from .audit import audit


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.print_usage(sys.stderr)
        self.exit(1, self.prog + ': error: ' + message + '\n')


def main(argv=None):
    parser = Parser(prog='streaming-claim-audit')
    parser.add_argument('path', nargs='?', default='.')
    parser.add_argument('--version', action='version', version=__version__)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--ignore', default='', metavar='RULE,...')
    parser.add_argument('--fail-on', choices=('MEDIUM', 'HIGH'), default='MEDIUM')
    args = parser.parse_args(argv)
    try:
        result = audit(args.path, {r.strip() for r in args.ignore.split(',')}, args.fail_on)
    except (OSError, ValueError, SyntaxError, UnicodeError) as error:
        print('streaming-claim-audit: error: ' + str(error), file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        for finding in result['findings']:
            print('{severity} {rule} {file}:{line} {message}'.format(**finding))
            for item in finding['evidence']:
                print('  {file}:{line} {kind}'.format(**item))
        if args.verbose:
            for claim in result['verified_claims']:
                print('VERIFIED {family} {file}:{line}'.format(**claim))
        print(result['summary']['status'])
    return 2 if result['summary']['status'] == 'FAIL' else 0


if __name__ == '__main__':
    sys.exit(main())
