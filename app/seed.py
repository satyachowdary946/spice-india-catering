from sqlalchemy import select
from sqlalchemy.orm import Session
from .models import BusinessSettings, Menu, Category, Subcategory, MenuItem


def ensure_seed_data(db: Session) -> None:
    if not db.get(BusinessSettings, 1):
        db.add(BusinessSettings(id=1))
        db.commit()

    if db.scalar(select(Menu.id).limit(1)):
        return

    # Demo structure only. Everything is editable in Admin > Menus.
    structures = [
        ("South Indian", "south-indian"),
        ("North Indian", "north-indian"),
    ]
    categories = ["Welcome Drink", "Starter", "Rice / Naan", "Main Course"]
    for menu_index, (menu_name, slug) in enumerate(structures):
        menu = Menu(name=menu_name, slug=slug, sort_order=menu_index)
        db.add(menu)
        db.flush()
        for c_index, category_name in enumerate(categories):
            category = Category(menu_id=menu.id, name=category_name, sort_order=c_index)
            db.add(category)
            db.flush()
            sub = Subcategory(category_id=category.id, name="Main Selection", sort_order=0)
            db.add(sub)
            db.flush()
            if category_name == "Starter":
                db.add_all([
                    MenuItem(subcategory_id=sub.id, name="Sample Veg Starter — edit me", dietary="veg", sort_order=0),
                    MenuItem(subcategory_id=sub.id, name="Sample Non-Veg Starter — edit me", dietary="nonveg", sort_order=1),
                ])
            elif category_name == "Main Course":
                db.add_all([
                    MenuItem(subcategory_id=sub.id, name="Sample Veg Main — edit me", dietary="veg", sort_order=0),
                    MenuItem(subcategory_id=sub.id, name="Sample Non-Veg Main — edit me", dietary="nonveg", sort_order=1),
                ])
    db.commit()
