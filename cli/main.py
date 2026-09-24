import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cli.splitter import cmd_split
from cli.merger import cmd_merge
from cli.downloader import cmd_download


def main():
    parser = argparse.ArgumentParser(
        description="文件分块下载工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""

更多帮助:
  python main.py split    -h   查看 split  命令的详细参数说明
  python main.py merge    -h   查看 merge  命令的详细参数说明
  python main.py download -h   查看 download 命令的详细参数说明
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    parser_split = subparsers.add_parser(
        'split',
        help='将本地大文件拆分为多个分片',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="将本地大文件拆分为多个固定大小的分片(.fk)，并生成一个 .fkx 信息文件记录所有分片的元数据",
        epilog="""
参数说明:
  -i, --input       要拆分的大文件路径，支持绝对路径和相对路径
  -o, --output      分片文件和 .fkx 信息文件的输出目录，目录不存在时会自动创建
  -c, --chunk-size  每个分片的大小（单位：MB），取值范围 1-1024，默认 10MB
                    数值越大分片数越少但单次传输压力越大，建议根据网络情况调整

使用示例:
  python main.py split -i D:\\iso\\win11.iso -o D:\\chunks -c 50    按 50MB 分块
  python main.py split -i ./large_file.zip -o ./output -c 100       按 100MB 分块
  python main.py split -i ./small.txt -o ./out                      默认 10MB 分块

输出文件:
  <文件名>.fkx          信息文件，记录文件名、大小、分片数和每个分片的元数据
  <文件名>-1.fk         第 1 个分片
  <文件名>-2.fk         第 2 个分片
  ...                   ...
        """
    )
    parser_split.add_argument('-i', '--input', required=True,
                              help='要分块的文件路径（必填）')
    parser_split.add_argument('-o', '--output', required=True,
                              help='输出目录（必填）')
    parser_split.add_argument('-c', '--chunk-size', type=int, default=10,
                              help='每个分片大小(MB), 范围1-1024, 默认10（可选）')
    parser_split.add_argument('-n', '--target-name', default=None,
                              help='目标文件名（可选，不指定则使用源文件名）')

    parser_merge = subparsers.add_parser(
        'merge',
        help='本地合并分片文件还原为原始文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="根据 .fkx 信息文件将本地的所有分片(.fk)合并还原为原始文件，并可选进行 SHA-256 校验",
        epilog="""
参数说明:
  -i, --input       .fkx 信息文件的路径，合并时会自动在同目录下查找对应的 .fk 分片
  -o, --output      合并后原始文件的输出目录
  -s, --skip-sha256 跳过 SHA-256 校验（可选标志）
                    默认会执行 SHA-256 完整性校验确保合并后的文件与原始文件一致
                    添加此参数可跳过校验以加快合并速度，适用于已验证过分片完整性的场景

使用示例:
  python main.py merge -i ./chunks/video.mp4.fkx -o ./output         标准合并+校验
  python main.py merge -i ./chunks/video.mp4.fkx -o ./output -s      跳过校验快速合并
  python main.py merge -i D:\\data\\file.iso.fkx -o D:\\restored      合并ISO文件
        """
    )
    parser_merge.add_argument('-i', '--input', required=True,
                              help='.fkx信息文件路径（必填）')
    parser_merge.add_argument('-o', '--output', required=True,
                              help='输出目录（必填）')
    parser_merge.add_argument('-s', '--skip-sha256', action='store_true',
                              help='跳过SHA-256校验以加快合并速度（可选标志）')

    parser_download = subparsers.add_parser(
        'download',
        help='远程下载分片并自动合并为原始文件',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="从远程服务器下载 .fkx 信息文件及其所有分片(.fk)，下载完成后自动合并为原始文件并校验完整性",
        epilog="""
参数说明:
  -u, --url         远程 .fkx 信息文件的完整 URL（必填）
                    程序会自动解析 URL 的路径前缀，从同目录下载对应的 .fk 分片
  -o, --output      下载和合并后文件的输出目录（必填）
  -e, --enhanced    启用增强下载模式（可选标志）
                    使用浏览器指纹伪装和 curl_cffi 库模拟 Chrome 131
                    适用于需要绕过反爬虫检测的服务器，需安装 curl_cffi
  -t, --timeout     每个分片下载的 HTTP 请求超时时间（单位：秒），默认 120（可选）
                    网络不稳定时可适当增大此值，如 -t 300
  -s, --skip-sha256 跳过下载完成后的 SHA-256 校验（可选标志）
                    默认会执行完整性校验，添加此参数可跳过以节省时间

断点续传:
  下载过程中如果中断，已下载的分片会保留在 <文件名>-fkxz 目录中
  再次执行相同的 download 命令即可从断点处继续下载，已完成的不会重复下载

使用示例:
  python main.py download -u https://example.com/files/video.mp4.fkx -o ./output
      标准模式下载

  python main.py download -u https://example.com/files/video.mp4.fkx -o ./output -e
      增强模式（浏览器指纹+curl_cffi）

  python main.py download -u https://example.com/files/video.mp4.fkx -o ./output -t 300
      设置超时为 300 秒（适合大文件或慢速网络）

  python main.py download -u https://example.com/files/video.mp4.fkx -o ./output -e -t 180 -s
      增强模式 + 180秒超时 + 跳过校验（组合使用）
        """
    )
    parser_download.add_argument('-u', '--url', required=True,
                                 help='.fkx信息文件的远程URL（必填）')
    parser_download.add_argument('-o', '--output', required=True,
                                 help='输出目录（必填）')
    parser_download.add_argument('-e', '--enhanced', action='store_true',
                                 help='启用增强模式：浏览器指纹伪装 + curl_cffi（可选标志）')
    parser_download.add_argument('-t', '--timeout', type=int, default=120,
                                 help='请求超时时间(秒)，默认120，建议网络差时增大（可选）')
    parser_download.add_argument('-s', '--skip-sha256', action='store_true',
                                 help='跳过SHA-256校验以节省时间（可选标志）')

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