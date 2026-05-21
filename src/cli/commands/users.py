"""CLI commands: users"""
from datetime import datetime

import numpy as np

from src.cli.helpers import (
    DEFAULT_ALLOCATIONS,
    add_alloc_arg,
    ensure_db,
    fail_result,
    get_allocations,
    is_a_share_trading_now,
    parse_allocations,
    print_portfolio_metrics,
)


def cmd_user_create(args):
    """創建用戶"""
    from src.core.auth import create_user

    ensure_db()

    try:
        user = create_user(args.username, args.password, role=args.role)
        print(f"✅ 用戶創建成功:")
        print(f"   ID:       {user.id}")
        print(f"   用戶名:   {user.username}")
        print(f"   角色:     {user.role}")
        print(f"   創建時間: {user.created_at}")
    except ValueError as e:
        print(f"❌ 創建失敗: {e}")




def cmd_user_list(args):
    """列出所有用戶"""
    from src.core.auth import list_users

    ensure_db()

    users = list_users()
    if not users:
        print("暫無用戶")
        return

    print(f"\n{'='*60}")
    print(f"📋 用戶列表 (共 {len(users)} 個)")
    print(f"{'='*60}")
    print(f"{'ID':>4} {'用戶名':<16} {'角色':<8} {'創建時間':<20}")
    print(f"{'-'*4} {'-'*16} {'-'*8} {'-'*20}")

    for u in users:
        role_icon = "👑" if u["role"] == "admin" else "👤"
        print(f"{u['id']:>4} {u['username']:<16} {role_icon}{u['role']:<7} {u.get('created_at', ''):<20}")




def cmd_user_reset_password(args):
    """重置用戶密碼"""
    from src.core.auth import get_user_by_username, reset_password

    ensure_db()

    user = get_user_by_username(args.username)
    if not user:
        print(f"❌ 用戶 '{args.username}' 不存在")
        return

    new_password = args.new_password
    if not new_password:
        import getpass
        new_password = getpass.getpass("請輸入新密碼: ")
        if not new_password:
            print("❌ 密碼不能為空")
            return
    success = reset_password(user.id, new_password)
    if success:
        print(f"✅ 密碼已重置:")
        print(f"   用戶名:   {args.username}")
        print(f"   新密碼:   {new_password}")
        print(f"   請盡快修改密碼！")
    else:
        print(f"❌ 重置失敗")


