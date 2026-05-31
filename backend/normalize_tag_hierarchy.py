from __future__ import annotations

from backend.app.db import SessionLocal
from backend.app.models import EntryTag


TAG_GROUPS = {
    "日常生活": {
        "生活实物",
        "食物",
        "蔬菜",
        "水果",
        "肉类",
        "海鲜鱼类",
        "乳制品",
        "面包点心",
        "零食",
        "饮料",
        "调料干货",
        "厨房",
        "浴室",
        "家具家居",
        "衣物",
        "工具",
        "文具",
        "超市购物",
        "电子用品",
    },
    "公共事务": {
        "政治场景",
        "政治通用",
        "政府机构",
        "政治制度",
        "政党议会",
        "选举投票",
        "法律政策",
        "社会议题",
        "国际关系",
        "政治新闻",
        "权利自由",
    },
    "经济金融": {
        "金融场景",
        "银行账户",
        "支付转账",
        "贷款信用",
        "投资证券",
        "税务",
        "保险",
        "收入预算",
        "公司财务",
        "宏观金融",
    },
    "交通出行": {
        "驾照理论",
        "车辆类型",
        "交通参与者",
        "交通状况",
        "道路场景",
        "交通标志",
        "交通规则",
        "事故应急",
        "危险因素",
        "车辆部件",
        "驾照法规",
        "驾驶动作",
        "方向位置",
    },
}

GRAMMAR_TAGS = {
    "名词",
    "noun",
    "verb",
    "adjective",
    "adverb",
    "conjunction",
    "反身动词",
    "非反身动词",
}

REMOVED_TAGS = {"der", "die", "das"}


def main() -> None:
    changed = 0
    removed = 0
    with SessionLocal() as session:
        removed = session.query(EntryTag).filter(EntryTag.name.in_(REMOVED_TAGS)).delete(
            synchronize_session=False
        )
        tags = session.query(EntryTag).all()
        for tag in tags:
            next_type = None
            for group, names in TAG_GROUPS.items():
                if tag.name in names:
                    next_type = group
                    break
            if tag.name in GRAMMAR_TAGS:
                next_type = "语言属性"
            if next_type and tag.tag_type != next_type:
                tag.tag_type = next_type
                changed += 1
        session.commit()
    print(f"Updated {changed} tag rows; removed {removed} article tag rows.")


if __name__ == "__main__":
    main()
