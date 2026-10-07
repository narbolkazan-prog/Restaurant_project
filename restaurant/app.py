import os
from datetime import datetime

from flask import Flask, render_template, session, redirect, url_for, request
from database import get_connection


app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "dev-only-change-me"
)


def get_cart_items(cursor, cart):

    ids = list(set(cart))

    if not ids:
        return []

    cursor.execute(
        """
        SELECT food_id, food_name, price
        FROM menu
        WHERE food_id = ANY(%s)
        ORDER BY food_id
        """,
        (ids,),
    )

    return [
        (food_id, name, price, cart.count(food_id))
        for food_id, name, price in cursor.fetchall()
    ]


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/menu/<int:page>")
def menu_page(page):

    categories = [
        "Fast Food",
        "Soups & Rice",
        "Pasta & Pizza",
        "Salads & Desserts",
        "Drinks"
    ]

    if page < 1:
        page = 1

    if page > len(categories):
        page = len(categories)

    category = categories[page - 1]

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT food_id, food_name, price, description
                FROM menu
                WHERE category = %s
                ORDER BY food_id
                """,
                (category,),
            )

            foods = cursor.fetchall()

    finally:
        connection.close()

    cart = session.get("cart", [])

    return render_template(
        "menu.html",
        foods=foods,
        category=category,
        page=page,
        total_pages=len(categories),
        cart=cart
    )


@app.route("/add_to_cart/<int:food_id>")
def add_to_cart(food_id):

    cart = session.get("cart", [])

    cart.append(food_id)

    session["cart"] = cart

    return redirect(url_for("home"))


@app.route("/increase/<int:food_id>")
def increase(food_id):

    cart = session.get("cart", [])

    cart.append(food_id)

    session["cart"] = cart

    return redirect(url_for("cart"))


@app.route("/decrease/<int:food_id>")
def decrease(food_id):

    cart = session.get("cart", [])

    if food_id in cart:
        cart.remove(food_id)

    session["cart"] = cart

    return redirect(url_for("cart"))


@app.route("/cart")
def cart():

    cart = session.get("cart", [])

    connection = get_connection()

    try:
        with connection.cursor() as cursor:
            cart_items = get_cart_items(cursor, cart)

    finally:
        connection.close()

    total = sum(
        item[2] * item[3]
        for item in cart_items
    )

    return render_template(
        "cart.html",
        cart_items=cart_items,
        total=total
    )


@app.route("/checkout", methods=["GET", "POST"])
def checkout():

    cart = session.get("cart", [])

    if not cart:
        return redirect(url_for("cart"))

    if request.method == "POST":

        name = request.form["name"]
        phone = request.form["phone"]
        email = request.form["email"]

        connection = get_connection()

        try:
            with connection:

                with connection.cursor() as cursor:

                    cart_items = get_cart_items(
                        cursor,
                        cart
                    )

                    total = sum(
                        item[2] * item[3]
                        for item in cart_items
                    )

                    cursor.execute(
                        """
                        INSERT INTO customers
                        (name, phone, email)
                        VALUES (%s, %s, %s)
                        RETURNING customer_id
                        """,
                        (
                            name,
                            phone,
                            email
                        ),
                    )

                    customer_id = cursor.fetchone()[0]

                    cursor.execute(
                        """
                        INSERT INTO orders
                        (
                            customer_id,
                            staff_id,
                            time,
                            status,
                            total_amount
                        )
                        VALUES (%s, %s, %s, %s, %s)
                        RETURNING order_id
                        """,
                        (
                            customer_id,
                            1,
                            datetime.now(),
                            "Pending",
                            total
                        ),
                    )

                    order_id = cursor.fetchone()[0]

                    for food_id, _, price, quantity in cart_items:

                        cursor.execute(
                            """
                            INSERT INTO order_items
                            (
                                order_id,
                                food_id,
                                quantity,
                                price
                            )
                            VALUES (%s, %s, %s, %s)
                            """,
                            (
                                order_id,
                                food_id,
                                quantity,
                                price
                            ),
                        )

                    cursor.execute(
                        """
                        SELECT
                            m.food_name,
                            oi.quantity,
                            oi.price
                        FROM order_items oi
                        JOIN menu m
                            ON oi.food_id = m.food_id
                        WHERE oi.order_id = %s
                        """,
                        (order_id,),
                    )

                    items = cursor.fetchall()

        finally:
            connection.close()

        session["cart"] = []

        return render_template(
            "order_success.html",
            order_id=order_id,
            items=items,
            total=total
        )

    return render_template("checkout.html")


if __name__ == "__main__":
    app.run(debug=True)