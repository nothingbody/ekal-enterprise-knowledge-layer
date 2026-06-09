"""
分页工具模块。

提供统一的分页响应结构与工具函数。
"""
from typing import TypeVar, Generic, List, Any
from dataclasses import dataclass

T = TypeVar("T")


@dataclass
class PaginatedResult(Generic[T]):
    """分页结果数据类。"""
    items: List[T]
    total: int
    page: int
    page_size: int
    pages: int

    def to_dict(self) -> dict:
        """转换为字典格式。"""
        return {
            "items": self.items,
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "pages": self.pages,
        }


def paginate(
    items: List[Any],
    total: int,
    page: int = 1,
    page_size: int = 20,
) -> PaginatedResult:
    """
    构建分页响应。

    :param items: 当前页的数据列表
    :param total: 总记录数
    :param page: 当前页码（从 1 开始）
    :param page_size: 每页条数
    :return: PaginatedResult 实例
    """
    pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    return PaginatedResult(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


def calculate_offset(page: int, page_size: int) -> int:
    """
    计算数据库查询偏移量。

    :param page: 页码（从 1 开始）
    :param page_size: 每页条数
    :return: 偏移量
    """
    return (max(1, page) - 1) * page_size


def validate_pagination(
    page: int,
    page_size: int,
    max_page_size: int = 100,
) -> tuple[int, int]:
    """
    验证并规范化分页参数。

    :param page: 页码
    :param page_size: 每页条数
    :param max_page_size: 每页最大条数
    :return: (规范化的 page, 规范化的 page_size)
    """
    page = max(1, page)
    page_size = max(1, min(page_size, max_page_size))
    return page, page_size
