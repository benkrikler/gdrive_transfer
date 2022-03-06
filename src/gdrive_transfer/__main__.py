from . import drive


def prep_parser():
    from argparse import ArgumentParser
    parser = ArgumentParser()
    parser.add_argument("-s", "--source", dest="source_id", required=True)
    parser.add_argument("-d", "--dest", dest="dest_id")
    parser.add_argument("-a", "--action", choices=("ls_json", "ls", "mv", "mkdir"), default="ls")
    return parser


if __name__ == "__main__":
    args = prep_parser().parse_args()
    if args.action == "ls":
        drive.ls(args.source_id)
    elif args.action == "ls_json":
        drive.ls(args.source_id, fmt="json" )
    elif args.action == "mv":
        if not dest_id in args:
            raise ValueError("Need to provide destination with `-d` or `--dest` for mv action")
        print(drive.recursive_move(**vars(args)))
    elif args.action == "mkdir":
        print(drive.create_folder(args.source_id, args.dest_id, "random_string"))
