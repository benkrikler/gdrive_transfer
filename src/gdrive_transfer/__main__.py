from . import drive
from . import testing


def prep_parser():
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("-s", "--source", dest="source_id", required=True)
    parser.add_argument("-d", "--dest", dest="dest_id")
    parser.add_argument("-a", "--action", choices=("ls_json", "ls", "mv", "mkdir", "mk_test", "own"), default="ls")
    parser.add_argument("-r", "--actually-run", default=False, action="store_true")
    return parser


if __name__ == "__main__":
    args = prep_parser().parse_args()
    if args.action == "ls":
        drive.ls(args.source_id)
    elif args.action == "ls_json":
        drive.ls(args.source_id, fmt="json" )
    elif args.action == "mv":
        if not "dest_id" in args:
            raise ValueError("Need to provide destination with `-d` or `--dest` for mv action")
        print(drive.recursive_move(args.source_id, args.dest_id, dry_run=not args.actually_run))
    elif args.action == "mkdir":
        print(drive.create_folder(args.source_id, args.dest_id, "random_string"))
    elif args.action == "mk_test":
        testing.create_test_structure_1(args.source_id)
    elif args.action == "own":
        drive.transfer_ownership(args.source_id)
