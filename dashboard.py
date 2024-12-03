import streamlit as st
import pandas as pd
import mysql.connector
from mysql.connector import Error

# we import ChatGroq class where our api key and model is store
from langchain_groq import ChatGroq

llm = ChatGroq(
    temperature=0,
    groq_api_key = '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',    
    model="llama-3.1-70b-versatile",
)

# used to test our model
response=llm.invoke("how to store data in .dat file python")
print(response.content)

def connect_to_database():
    try:
        connection = mysql.connector.connect(
            host="localhost",
            user="root",
            password="password",
            database="inventory_db"
        )
        return connection
    except Error as e:
        st.error(f"Error connecting to MySQL: {e}")
        return None
from pymongo import MongoClient

def connect_to_mongodb():
    try:
        client = MongoClient("mongodb+srv://mcenroeryan23:yfCPEu6baJt0syJZ@mymongocluster.vzfgh.mongodb.net/")
        db = client["inventory_db"] 
        return db
    except Exception as e:
        st.error(f"Error connecting to MongoDB: {e}")
        return None

def fetch_table_data(connection, query):
    try:
        cursor = connection.cursor(dictionary=True)
        cursor.execute(query)
        rows = cursor.fetchall()
        return pd.DataFrame(rows)
    except Error as e:
        st.error(f"Error fetching data: {e}")
        return pd.DataFrame()

def execute_query(connection, query, params=None):
    try:
        cursor = connection.cursor()
        cursor.execute(query, params)
        connection.commit()
        return True
    except Error as e:
        st.error(f"Error executing query: {e}")
        return False

def add_order(connection):
    st.header("Add Order")

    # Input fields for Order
    supplier_id = st.number_input("Supplier ID", min_value=1, step=1)
    order_date = st.date_input("Order Date")
    status = st.selectbox("Order Status", ["Pending", "Shipped", "Delivered"])

    # Input fields for Order Items
    st.subheader("Order Items")
    product_id = st.number_input("Product ID", min_value=1, step=1)
    quantity = st.number_input("Quantity", min_value=1, step=1)
    price = st.number_input("Price per Unit", min_value=0.0, step=0.01)

    if st.button("Add Order"):
        try:
            # Start a transaction
            cursor = connection.cursor()

            # Insert into Order table
            query_order = """
                INSERT INTO `Order` (SupplierID, OrderDate, Status)
                VALUES (%s, %s, %s)
            """
            cursor.execute(query_order, (supplier_id, order_date, status))
            order_id = cursor.lastrowid  # Get the last inserted OrderID

            # Insert into OrderItem table
            query_order_item = """
                INSERT INTO OrderItem (OrderID, ProductID, Quantity, Price)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(query_order_item, (order_id, product_id, quantity, price))

            # Update inventory
            query_update_inventory = """
                UPDATE Inventory
                SET Quantity = Quantity - %s
                WHERE ProductID = %s
            """
            cursor.execute(query_update_inventory, (quantity, product_id))

            # Commit the transaction
            connection.commit()
            st.success(f"Order {order_id} added successfully and inventory updated!")
        except Error as e:
            # Rollback in case of an error
            connection.rollback()
            st.error(f"Error adding order or updating inventory: {e}")

from bson import Decimal128
from datetime import datetime, date
from decimal import Decimal  


def delete_order(connection, mongodb):
    st.header("Delete Order")

    # Input field for Order ID
    order_id = st.number_input("Enter Order ID to Delete", min_value=1, step=1)

    if st.button("Delete Order"):
        try:
            # Fetch order details before deletion
            query_order = "SELECT * FROM `Order` WHERE OrderID = %s"
            order_data = fetch_table_data(connection, query_order % order_id)

            if not order_data.empty:
                # Fetch associated order items
                query_order_items = "SELECT * FROM `OrderItem` WHERE OrderID = %s"
                order_items_data = fetch_table_data(connection, query_order_items % order_id)

                # Fetch associated shipment details
                query_shipment = "SELECT * FROM `Shipment` WHERE OrderID = %s"
                shipment_data = fetch_table_data(connection, query_shipment % order_id)

                # Function to convert incompatible types (datetime.date, decimal.Decimal)
                def convert_types(record):
                    for key, value in record.items():
                        if isinstance(value, date):  # Convert date to datetime
                            record[key] = datetime.combine(value, datetime.min.time())
                        elif isinstance(value, Decimal):  # Convert Decimal to float
                            record[key] = float(value)
                    return record

                # Prepare data for MongoDB
                order_data_dict = order_data.to_dict("records")
                order_items_data_dict = order_items_data.to_dict("records")
                shipment_data_dict = shipment_data.to_dict("records")
                converted_order = [convert_types(record) for record in order_data_dict]
                converted_items = [convert_types(record) for record in order_items_data_dict]
                converted_shipments = [convert_types(record) for record in shipment_data_dict]

                # Insert the deleted order, items, and shipments into MongoDB
                order_history = {
                    "Order": converted_order,
                    "OrderItems": converted_items,
                    "Shipments": converted_shipments,
                    "DeletedAt": datetime.now().isoformat()
                }
                mongodb["deleted_order"].insert_one(order_history)

                # Delete associated rows from Shipment table
                delete_shipment_query = "DELETE FROM `Shipment` WHERE OrderID = %s"
                cursor = connection.cursor()
                cursor.execute(delete_shipment_query, (order_id,))

                # Verify rows are deleted from Shipment
                cursor.execute("SELECT COUNT(*) FROM `Shipment` WHERE OrderID = %s", (order_id,))
                remaining_shipments = cursor.fetchone()[0]
                if remaining_shipments > 0:
                    raise Exception("Failed to delete associated rows from `Shipment`.")

                # Delete associated rows from OrderItem table
                delete_order_items_query = "DELETE FROM `OrderItem` WHERE OrderID = %s"
                cursor.execute(delete_order_items_query, (order_id,))

                # Verify rows are deleted from OrderItem
                cursor.execute("SELECT COUNT(*) FROM `OrderItem` WHERE OrderID = %s", (order_id,))
                remaining_items = cursor.fetchone()[0]
                if remaining_items > 0:
                    raise Exception("Failed to delete associated rows from `OrderItem`.")

                # Delete the order from the Order table
                delete_order_query = "DELETE FROM `Order` WHERE OrderID = %s"
                cursor.execute(delete_order_query, (order_id,))
                connection.commit()

                st.success(f"Order {order_id} and its associated items and shipments were deleted successfully and recorded in MongoDB.")
            else:
                st.warning(f"Order ID {order_id} not found.")
        except Error as e:
            connection.rollback()
            st.error(f"Error deleting order from MySQL: {e}")
        except Exception as e:
            st.error(f"Error interacting with MongoDB or cleaning up dependencies: {e}")


# Track Order
def track_order(connection):
    st.header("Track Order")

    # Input field for Order ID
    order_id = st.number_input("Enter Order ID to Track", min_value=1, step=1)

    if st.button("Track Order"):
        try:
            # Query to fetch Shipment details for the order
            query = """
                SELECT 
                    Shipment.ShipmentID, 
                    Shipment.ShipmentDate, 
                    Shipment.TrackingNumber, 
                    `Order`.Status
                FROM Shipment
                LEFT JOIN `Order` ON Shipment.OrderID = `Order`.OrderID
                WHERE `Order`.OrderID = %s
            """
            shipment_data = fetch_table_data(connection, query % order_id)

            if not shipment_data.empty:
                st.write("Order Shipment Details:")
                st.dataframe(shipment_data, use_container_width=True)
            else:
                st.warning("No shipment details found for the given Order ID.")
        except Error as e:
            st.error(f"Error fetching shipment details: {e}")

def modify_order(connection):
    st.header("Modify Order")

    # Initialize session state for order details if not set
    if "order_details" not in st.session_state:
        st.session_state["order_details"] = None
    if "order_items" not in st.session_state:
        st.session_state["order_items"] = None

    # Input to select Order ID
    order_id = st.number_input("Enter Order ID to Modify", min_value=1, step=1)

    # Fetch Order Details
    if st.button("Fetch Order Details"):
        try:
            # Fetch order details from the database
            query_order = """
                SELECT OrderID, SupplierID, OrderDate, Status
                FROM `Order`
                WHERE OrderID = %s
            """
            order_data = fetch_table_data(connection, query_order % order_id)

            if not order_data.empty:  # Check if DataFrame is not empty
                st.session_state["order_details"] = order_data.iloc[0]

                # Fetch associated Order Items
                query_items = """
                    SELECT OrderItemID, ProductID, Quantity, Price
                    FROM OrderItem
                    WHERE OrderID = %s
                """
                items_data = fetch_table_data(connection, query_items % order_id)
                st.session_state["order_items"] = items_data
            else:
                st.warning("Order ID not found.")
        except Error as e:
            st.error(f"Error fetching order details: {e}")

    # Display and Update Order Details
    if st.session_state["order_details"] is not None:
        order_details = st.session_state["order_details"]
        st.write("**Order Details:**")
        
        supplier_id = st.number_input(
            "Supplier ID", value=order_details["SupplierID"], step=1, key="supplier_id"
        )
        order_date = st.date_input(
            "Order Date", value=pd.to_datetime(order_details["OrderDate"]), key="order_date"
        )
        status = st.selectbox(
            "Order Status",
            ["Pending", "Shipped", "Delivered"],
            index=["Pending", "Shipped", "Delivered"].index(order_details["Status"]),
            key="order_status",
        )

        # Display and Update Order Items
        if st.session_state["order_items"] is not None and not st.session_state["order_items"].empty:
            items_data = st.session_state["order_items"]
            st.write("**Order Items:**")
            updated_items = []

            for _, item in items_data.iterrows():
                st.write(f"Item ID: {item['OrderItemID']}")
                product_id = st.number_input(
                    f"Product ID (Item {item['OrderItemID']})",
                    value=item["ProductID"],
                    step=1,
                    key=f"prod_{item['OrderItemID']}",
                )
                quantity = st.number_input(
                    f"Quantity (Item {item['OrderItemID']})",
                    value=item["Quantity"],
                    step=1,
                    key=f"qty_{item['OrderItemID']}",
                )
                price = st.number_input(
                    f"Price (Item {item['OrderItemID']})",
                    value=float(item["Price"]),
                    step=0.01,
                    key=f"price_{item['OrderItemID']}",
                )

                updated_items.append(
                    {
                        "OrderItemID": item["OrderItemID"],
                        "ProductID": product_id,
                        "Quantity": quantity,
                        "Price": price,
                    }
                )

            # Update Order Items Button
            if st.button("Update Order Items"):
                try:
                    for item in updated_items:
                        query_update_item = """
                            UPDATE OrderItem
                            SET ProductID = %s, Quantity = %s, Price = %s
                            WHERE OrderItemID = %s
                        """
                        execute_query(
                            connection,
                            query_update_item,
                            (item["ProductID"], item["Quantity"], item["Price"], item["OrderItemID"]),
                        )
                    st.success("Order items updated successfully!")
                except Error as e:
                    st.error(f"Error updating order items: {e}")

        # Update Order Details Button
        if st.button("Update Order Details"):
            try:
                query_update_order = """
                    UPDATE `Order`
                    SET SupplierID = %s, OrderDate = %s, Status = %s
                    WHERE OrderID = %s
                """
                execute_query(
                    connection,
                    query_update_order,
                    (supplier_id, order_date, status, order_id),
                )
                st.success("Order details updated successfully!")
            except Error as e:
                st.error(f"Error updating order details: {e}")


# Supplier Details
def supplier_details(connection):
    st.header("Supplier Details")

    # Query to fetch supplier details with associated products and categories
    query = """
        SELECT 
            Supplier.SupplierID,
            Supplier.SupplierName,
            Supplier.ContactInfo,
            Product.ProductName,
            Category.CategoryName,
            Product.Price,
            Product.Quantity
        FROM Supplier
        LEFT JOIN Product ON Supplier.SupplierID = Product.ProductID
        LEFT JOIN Category ON Product.CategoryID = Category.CategoryID
        ORDER BY Supplier.SupplierName
    """
    supplier_data = fetch_table_data(connection, query)

    if not supplier_data.empty:
        st.dataframe(supplier_data, use_container_width=True)
    else:
        st.info("No supplier details found.")

def get_supplier_details(connection):
    st.header("View Supplier Details")

    query = """
        SELECT 
            SupplierID,
            SupplierName,
            ContactInfo
        FROM Supplier
        ORDER BY SupplierName
    """
    supplier_data = fetch_table_data(connection, query)

    if not supplier_data.empty:
        st.dataframe(supplier_data, use_container_width=True)
    else:
        st.info("No supplier details found.")

def add_supplier(connection):
    st.header("Add Supplier")

    supplier_name = st.text_input("Supplier Name")
    contact_info = st.text_input("Contact Information")

    if st.button("Add Supplier"):
        if supplier_name and contact_info:
            query = """
                INSERT INTO Supplier (SupplierName, ContactInfo)
                VALUES (%s, %s)
            """
            if execute_query(connection, query, (supplier_name, contact_info)):
                st.success(f"Supplier '{supplier_name}' added successfully!")
        else:
            st.error("Please fill in all fields.")

def delete_supplier(connection):
    st.header("Delete Supplier")

    supplier_id = st.number_input("Enter Supplier ID to Delete", min_value=1, step=1)

    if st.button("Delete Supplier"):
        query = "DELETE FROM Supplier WHERE SupplierID = %s"
        if execute_query(connection, query, (supplier_id,)):
            st.success(f"Supplier ID {supplier_id} deleted successfully!")
        else:
            st.error("Failed to delete supplier. Please check the Supplier ID.")

def customer_insights(connection):
    st.header("Customer Purchase Insights")
    query = """
        SELECT 
            Customer.CustomerName, 
            COUNT(Sales.SalesID) AS TotalPurchases, 
            SUM(Sales.SaleAmount) AS TotalSpent
        FROM Customer
        JOIN Sales ON Customer.CustomerID = Sales.CustomerID
        GROUP BY Customer.CustomerName
        ORDER BY TotalSpent DESC
    """
    customer_data = fetch_table_data(connection, query)
    if not customer_data.empty:
        st.bar_chart(customer_data, x="CustomerName", y="TotalSpent", use_container_width=True)
        st.write("Detailed Insights:")
        st.dataframe(customer_data, use_container_width=True)
    else:
        st.info("No customer purchase data available.")

def supplier_performance_dashboard(connection):
    st.header("Supplier Performance")
    query = """
        SELECT 
            Supplier.SupplierName, 
            COUNT(Product.ProductID) AS ProductsSupplied, 
            SUM(Product.Quantity) AS TotalQuantity
        FROM Supplier
        JOIN Product ON Supplier.SupplierID = Product.ProductID
        GROUP BY Supplier.SupplierName
        ORDER BY TotalQuantity DESC
    """
    supplier_data = fetch_table_data(connection, query)
    if not supplier_data.empty:
        st.bar_chart(supplier_data, x="SupplierName", y="TotalQuantity", use_container_width=True)
        st.dataframe(supplier_data, use_container_width=True)
    else:
        st.info("No supplier data available.")

def customer_insights(connection):
    st.header("Customer Insights")

    # Tabs for different insights
    tab1, tab2 = st.tabs(["Top Customers","Customer Segmentation"])

    # Tab 1: Top Customers by Revenue
    with tab1:
        st.subheader("Top Customers by Revenue")
        query = """
            SELECT 
                Customer.CustomerName AS Customer,
                SUM(Sales.SaleAmount) AS TotalSpent,
                COUNT(Sales.SalesID) AS TotalOrders
            FROM Customer
            LEFT JOIN Sales ON Customer.CustomerID = Sales.CustomerID
            GROUP BY Customer.CustomerName
            ORDER BY TotalSpent DESC
            LIMIT 10
        """
        top_customers = fetch_table_data(connection, query)

        if not top_customers.empty:
            st.bar_chart(data=top_customers, x="Customer", y="TotalSpent", use_container_width=True)
            st.dataframe(top_customers, use_container_width=True)
        else:
            st.info("No data available for top customers.")

    # Tab 2: Customer Segmentation
    with tab2:
        st.subheader("Customer Segmentation")
        query = """
            SELECT 
                Customer.CustomerName AS Customer,
                COUNT(Sales.SalesID) AS TotalOrders,
                CASE 
                    WHEN COUNT(Sales.SalesID) >= 5 THEN 'Regular'
                    ELSE 'Occasional'
                END AS CustomerType
            FROM Customer
            LEFT JOIN Sales ON Customer.CustomerID = Sales.CustomerID
            GROUP BY Customer.CustomerName
        """
        segmentation_data = fetch_table_data(connection, query)

        if not segmentation_data.empty:
            st.dataframe(segmentation_data, use_container_width=True)
            regular_customers = segmentation_data[segmentation_data["CustomerType"] == "Regular"]
            occasional_customers = segmentation_data[segmentation_data["CustomerType"] == "Occasional"]

            st.write(f"**Number of Regular Customers:** {len(regular_customers)}")
            st.write(f"**Number of Occasional Customers:** {len(occasional_customers)}")
        else:
            st.info("No data available for customer segmentation.")

def main():
    st.title("Inventory Management System")

    # Connect to the database
    connection = connect_to_database()
    mongodb_connection = connect_to_mongodb() 

    if connection is not None and mongodb_connection is not None:
        # Sidebar menu
        st.sidebar.title("Menu")
        main_menu = st.sidebar.selectbox(
            "Select Main Menu", ["Inventory", "Orders", "Discounts", "Shipments", "Suppliers", "Customer Insights", "Insights"]
        )

        # Dashboard menu
        if main_menu == "Inventory":
            st.header("Inventory")
            submenu = st.sidebar.radio("Options", ["View Inventory"])

            if submenu == "View Inventory":
                query = """
                    SELECT 
                        Product.ProductName, 
                        Inventory.Quantity, 
                        Location.LocationName, 
                        Location.Address, 
                        Inventory.LastRestockDate
                    FROM Inventory
                    LEFT JOIN Product ON Inventory.ProductID = Product.ProductID
                    LEFT JOIN Location ON Inventory.LocationID = Location.LocationID
                """
                inventory_data = fetch_table_data(connection, query)
                if not inventory_data.empty:
                    st.dataframe(inventory_data, use_container_width=True)
                else:
                    st.info("No inventory records found.")

        elif main_menu == "Orders":
            st.header("Orders")
            submenu = st.sidebar.radio("Options", ["Add Order", "Delete Order", "Check Stock Availability", "Track Order", "Modify Order"])

            if submenu == "Add Order":
                add_order(connection)

            elif submenu == "Delete Order":
                delete_order(connection, mongodb_connection)

            elif submenu == "Check Stock Availability":
                st.header("Check Stock Availability")
                product_id = st.number_input("Enter Product ID", min_value=1, step=1)
                required_quantity = st.number_input("Enter Required Quantity", min_value=1, step=1)

                if st.button("Check Availability"):
                    query = """
                        SELECT 
                            Product.ProductName, 
                            Inventory.Quantity AS AvailableStock, 
                            Location.LocationName, 
                            Location.Address
                        FROM Inventory
                        LEFT JOIN Product ON Inventory.ProductID = Product.ProductID
                        LEFT JOIN Location ON Inventory.LocationID = Location.LocationID
                        WHERE Inventory.ProductID = %s
                    """
                    cursor = connection.cursor(dictionary=True)
                    cursor.execute(query, (product_id,))
                    stock_data = cursor.fetchall()

                    if stock_data:
                        stock_df = pd.DataFrame(stock_data)
                        total_stock = stock_df['AvailableStock'].sum()
                        sufficient_stock = total_stock >= required_quantity

                        st.write("Stock Details:")
                        st.dataframe(stock_df)

                        st.write(f"Total Available Stock: **{total_stock}**")
                        if sufficient_stock:
                            st.success("Sufficient stock is available.")
                        else:
                            st.error("Insufficient stock.")
                    else:
                        st.warning("Product not found in inventory.")

            elif submenu == "Track Order":
                track_order(connection)

            elif submenu == "Modify Order":
                modify_order(connection)

        elif main_menu == "Discounts":
            st.header("Discounts")
            submenu = st.sidebar.radio("Options", ["View Discounts", "Modify Discount"])

            if submenu == "View Discounts":
                query = """
                    SELECT 
                        Discount.DiscountID, 
                        Product.ProductName AS ProductName, 
                        Discount.DiscountPercent, 
                        Discount.StartDate, 
                        Discount.EndDate
                    FROM Discount
                    LEFT JOIN Product ON Discount.ProductID = Product.ProductID
                """
                discount_data = fetch_table_data(connection, query)
                if not discount_data.empty:
                    st.dataframe(discount_data, use_container_width=True)
                else:
                    st.info("No discounts available.")

            elif submenu == "Modify Discount":
                st.header("Modify Discount")
                query = """
                    SELECT 
                        Discount.DiscountID, 
                        Product.ProductName AS ProductName, 
                        Discount.DiscountPercent, 
                        Discount.StartDate, 
                        Discount.EndDate
                    FROM Discount
                    LEFT JOIN Product ON Discount.ProductID = Product.ProductID
                """
                discount_data = fetch_table_data(connection, query)

                if discount_data.empty:
                    st.warning("No discounts found to modify.")
                else:
                    st.write("Available Discounts:")
                    st.dataframe(discount_data)

                    discount_id = st.number_input("Enter Discount ID to Modify", min_value=1, step=1)

                    selected_discount = discount_data[discount_data["DiscountID"] == discount_id]

                    if not selected_discount.empty:
                        selected_discount = selected_discount.iloc[0]

                        st.write(f"**Selected Product:** {selected_discount['ProductName']}")
                        st.write(f"**Current Discount:** {selected_discount['DiscountPercent']}%")
                        st.write(f"**Start Date:** {selected_discount['StartDate']}")
                        st.write(f"**End Date:** {selected_discount['EndDate']}")

                        current_discount = float(selected_discount["DiscountPercent"])

                        new_discount_percent = st.number_input(
                            "New Discount Percent",
                            min_value=0.0,
                            max_value=100.0,
                            step=0.1,
                            value=current_discount,
                        )
                        new_start_date = st.date_input(
                            "New Start Date", value=pd.to_datetime(selected_discount["StartDate"])
                        )
                        new_end_date = st.date_input(
                            "New End Date", value=pd.to_datetime(selected_discount["EndDate"])
                        )

                        if st.button("Update Discount"):
                            update_query = """
                                UPDATE Discount
                                SET DiscountPercent = %s, StartDate = %s, EndDate = %s
                                WHERE DiscountID = %s
                            """
                            if execute_query(connection, update_query, (new_discount_percent, new_start_date, new_end_date, discount_id)):
                                st.success("Discount updated successfully!")

                                # Refresh the data after updating
                                refreshed_data = fetch_table_data(connection, query)
                                st.write("Updated Discounts:")
                                if not refreshed_data.empty:
                                    st.dataframe(refreshed_data, use_container_width=True)
                                else:
                                    st.info("No discounts available.")
                            else:
                                st.error("Failed to update the discount.")
                    else:
                        st.warning("Discount ID not found. Please enter a valid Discount ID.")

        elif main_menu == "Shipments":
            st.header("Shipments")

            status_filter = st.selectbox("Select Shipment Status", ["All", "Pending", "Shipped", "Delivered"])

            if status_filter == "All":
                query = """
                    SELECT 
                        Shipment.ShipmentID, 
                        Shipment.ShipmentDate, 
                        Shipment.TrackingNumber, 
                        `Order`.OrderID, 
                        `Order`.Status
                    FROM Shipment
                    LEFT JOIN `Order` ON Shipment.OrderID = `Order`.OrderID
                """
            elif status_filter == "Pending":
                query = """
                    SELECT 
                        Shipment.ShipmentID, 
                        Shipment.ShipmentDate, 
                        Shipment.TrackingNumber, 
                        `Order`.OrderID, 
                        `Order`.Status
                    FROM Shipment
                    LEFT JOIN `Order` ON Shipment.OrderID = `Order`.OrderID
                    WHERE `Order`.Status = "%s"
                """
            elif status_filter == "Shipped":
                query = """
                    SELECT 
                        Shipment.ShipmentID, 
                        Shipment.ShipmentDate, 
                        Shipment.TrackingNumber, 
                        `Order`.OrderID, 
                        `Order`.Status
                    FROM Shipment
                    LEFT JOIN `Order` ON Shipment.OrderID = `Order`.OrderID
                    WHERE `Order`.Status = "%s"
                """
            elif status_filter == "Delivered":
                query = """
                    SELECT 
                        Shipment.ShipmentID, 
                        Shipment.ShipmentDate, 
                        Shipment.TrackingNumber, 
                        `Order`.OrderID, 
                        `Order`.Status
                    FROM Shipment
                    LEFT JOIN `Order` ON Shipment.OrderID = `Order`.OrderID
                    WHERE `Order`.Status = "%s"
                """
            # Fetch filtered data
            if status_filter == "All":
                shipment_data = fetch_table_data(connection, query)
            else:
                shipment_data = fetch_table_data(connection, query % status_filter)

            # Display results
            if not shipment_data.empty:
                st.dataframe(shipment_data, use_container_width=True)
            else:
                st.info("No shipments found for the selected status.")

        elif main_menu == "Suppliers":
            st.header("Supplier Management")
            submenu = st.sidebar.radio("Options", ["View Suppliers", "Add Supplier", "Delete Supplier", "Modify Supplier"])

            if submenu == "View Suppliers":
                get_supplier_details(connection)

            elif submenu == "Add Supplier":
                add_supplier(connection)

            elif submenu == "Delete Supplier":
                delete_supplier(connection)

        elif main_menu == "Customer Insights":
            customer_insights(connection)

        elif main_menu == "Insights":
            dashboard_tab = st.sidebar.radio(
                "Dashboard Insights",
                ["Supplier Performance"]
            )
            if dashboard_tab == "Supplier Performance":
                supplier_performance_dashboard(connection)

        connection.close()
    else:
        st.error("Unable to connect to the database.")


if __name__ == "__main__":
    main()
