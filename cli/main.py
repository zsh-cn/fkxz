import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli.splitter import cmd_split
from cli.merger import cmd_merge
from cli.downloader import cmd_download


def main():
    parser = argparse.ArgumentParser(
        description="文件分块下载",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python main.py split  -i ./video.mp4 -o ./chunks -c 10
  python main.py merge  -i ./chunks/video.mp4.fkx -o ./output
  python main.py download -u https://example.com/files/video.mp4.fkx -o ./output
  python main.py download -u https://example.com/files/video.mp4.fkx -o ./output --enhanced
  python main.py download -u https://example.com/files/video.mp4.fkx -o ./output -t 300
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    parser_split = subparsers.add_parser('split', help='拆分文件为分片')
    parser_split.add_argument('-i', '--input', required=True, help='要拆分的文件路径')
    parser_split.add_argument('-o', '--output', required=True, help='输出目录')
    parser_split.add_argument('-c', '--chunk-size', type=int, default=10,
                              help='每个分片大小(MB), 范围1-1024, 默认10')

    parser_merge = subparsers.add_parser('merge', help='本地合并分片文件')
    parser_merge.add_argument('-i', '--input', required=True, help='.fkx信息文件路径')
    parser_merge.add_argument('-o', '--output', required=True, help='输出目录')

    parser_download = subparsers.add_parser('download', help='远程下载并合并文件')
    parser_download.add_argument('-u', '--url', required=True, help='.fkx信息文件的URL')
    parser_download.add_argument('-o', '--output', required=True, help='输出目录')
    parser_download.add_argument('-e', '--enhanced', action='store_true',
                                 help='启用增强模式 (浏览器指纹伪装 + curl_cffi)')
    parser_download.add_argument('-t', '--timeout', type=int, default=120,
                                 help='请求超时时间(秒), 默认120')

    args = parser.parse_args()

    if args.command == 'split':
        cmd_split(args)
    elif args.command == 'merge':
        cmd_merge(args)
    elif args.command == 'download':
        cmd_download(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()