import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli.splitter import cmd_split
from cli.merger import cmd_merge
from cli.downloader import cmd_download


def main():
    EPILOG = r"""

============================ 命令与参数说明 ============================

  split   将本地大文件拆分为多个固定大小的分片(.fk)，
          并生成一个 .fkx 信息文件记录所有分片的元数据

    参数:
      -i, --input        要拆分的大文件路径，支持绝对路径和相对路径（必填）
      -o, --output       分片文件和 .fkx 信息文件的输出目录，
                         目录不存在时会自动创建（必填）
      -n, --output-name  输出文件名（可选，不指定则使用源文件名）
      -c, --chunk-size   每个分片的大小（单位：MB），
                         取值范围 1-1024，默认 10MB

    输出文件:
      <文件名>.fkx      信息文件，记录文件名、大小、分片数和分片元数据
      <文件名>-1.fk     第 1 个分片
      <文件名>-2.fk     第 2 个分片
      ...               ...

-----------------------------------------------------------------------

  merge   根据 .fkx 信息文件将本地的所有分片(.fk)合并还原为原始文件，
          并可选进行 SHA-256 校验

    参数:
      -i, --input        .fkx 信息文件的路径，
                         合并时会自动在同目录下查找对应的 .fk 分片（必填）
      -o, --output       合并后原始文件的输出目录（必填）
      -s, --skip-sha256  跳过 SHA-256 校验（可选标志）

-----------------------------------------------------------------------

  download  从远程服务器下载 .fkx 信息文件及其所有分片(.fk)，
            下载完成后自动合并为原始文件并校验完整性

    参数:
      -u, --url          远程 .fkx 信息文件的完整 URL（必填）
                         程序会自动解析 URL 的路径前缀，
                         从同目录下载对应的 .fk 分片
      -o, --output       下载和合并后文件的输出目录（必填）
      -e, --enhanced     启用增强下载模式（可选标志）
                         使用浏览器指纹伪装和 curl_cffi 库模拟 Chrome 131，
                         适用于绕过反爬虫检测的服务器
      -t, --timeout      每个分片下载的 HTTP 请求超时时间（秒），
                         默认 120，网络不稳定时可适当增大（可选）
      -s, --skip-sha256  跳过下载完成后的 SHA-256 校验（可选标志）

    断点续传:
      下载过程中如果中断，已下载的分片会保留在
      <文件名>-fkxz 目录中。再次执行相同的 download 命令
      即可从断点处继续下载，已完成的不会重复下载

=======================================================================
"""

    parser = argparse.ArgumentParser(
        description="文件分块下载工具 — 大文件分片传输",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EPILOG,
    )

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    parser_split = subparsers.add_parser(
        'split',
        help='将本地大文件拆分为多个分片',
        description="将本地大文件拆分为多个固定大小的分片(.fk)，并生成一个 .fkx 信息文件",
    )
    parser_split.add_argument('-i', '--input', required=True,
                              help='要分块的文件路径')
    parser_split.add_argument('-o', '--output', required=True,
                              help='输出目录')
    parser_split.add_argument('-c', '--chunk-size', type=int, default=10,
                              help='每个分片大小(MB)，范围 1-1024，默认 10')
    parser_split.add_argument('-n', '--output-name', default=None,
                              help='输出文件名（可选，不指定则使用源文件名）')

    parser_merge = subparsers.add_parser(
        'merge',
        help='本地合并分片文件还原为原始文件',
        description="根据 .fkx 信息文件将本地的所有分片(.fk)合并还原为原始文件",
    )
    parser_merge.add_argument('-i', '--input', required=True,
                              help='.fkx 信息文件路径')
    parser_merge.add_argument('-o', '--output', required=True,
                              help='输出目录')
    parser_merge.add_argument('-s', '--skip-sha256', action='store_true',
                              help='跳过 SHA-256 校验')

    parser_download = subparsers.add_parser(
        'download',
        help='远程下载分片并自动合并为原始文件',
        description="从远程服务器下载 .fkx 信息文件及其所有分片(.fk)，下载完成后自动合并为原始文件并校验完整性",
    )
    parser_download.add_argument('-u', '--url', required=True,
                                 help='.fkx 信息文件的远程 URL')
    parser_download.add_argument('-o', '--output', required=True,
                                 help='输出目录')
    parser_download.add_argument('-e', '--enhanced', action='store_true',
                                 help='启用增强模式：浏览器指纹伪装 + curl_cffi')
    parser_download.add_argument('-t', '--timeout', type=int, default=120,
                                 help='请求超时时间(秒)，默认 120')
    parser_download.add_argument('-s', '--skip-sha256', action='store_true',
                                 help='跳过 SHA-256 校验')

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