#!/usr/bin/python

from PyQt5.QtWidgets import QWidget, QLabel, QMessageBox, QTableWidget, QAbstractItemView, QPushButton, \
                            QVBoxLayout, QDialog, QDialogButtonBox, QTableWidgetItem, QHeaderView

from PyQt5.QtCore import Qt

from datetime import timedelta, datetime, timezone
from dateutil.tz import tzutc

from convenience.server_apis import make_http_request, user_is_admin
from convenience.datetime_management import datetime_UTC_to_local

from entities.user import User
from entities.parking_lot import ParkingLot
from entities.parking_slot import ParkingSlot
from entities.booking import Booking
from entities.vehicle import Vehicle


class DetailsDialog(QDialog):
    def __init__(self, user, booking, vehicle_info, parking_slot_info, https_session, only_expired, parent = None):
        super().__init__(parent=parent)

        booking_info_dialog = [ ("Datetime start:", booking.get_datetime_start()),
                                ("Datetime end:", booking.get_datetime_end()),
                                ("Entry time:", booking.get_entry_time()),
                                ("Exit time:", booking.get_exit_time()),
                                ("Amount:", booking.get_amount()),
                                ("", "")]

        if vehicle_info != None:
            booking_info_dialog.extend([("Vehicle info:", ""),
                                        ("License plate:", vehicle_info.get_license_plate()),
                                        ("Brand:", vehicle_info.get_brand()),
                                        ("Model:", vehicle_info.get_model()),
                                        ("", "")])

        if parking_slot_info != None:
            booking_info_dialog.extend([("Parking slot info:", ""),
                                        ("Parking lot name:", parking_slot_info[0]),
                                        ("Parking lot street:", parking_slot_info[1]),
                                        ("Parking slot number:",parking_slot_info[2]),
                                        ("", ""),
                                        ("Note:", booking.get_note())])

        self.setWindowTitle("Booking details")

        self.buttonBox = QDialogButtonBox(QDialogButtonBox.Ok)
        ok_button = self.buttonBox.button(QDialogButtonBox.Ok)
        ok_button.setAutoDefault(True)
        ok_button.setDefault(True)
        self.buttonBox.accepted.connect(self.accept)        # QDialog slot

        if not user_is_admin(user, https_session) and not only_expired:             # admin can't delete user bookings and expired bookings can't be deleted
            delete_button = self.buttonBox.addButton("Delete", QDialogButtonBox.RejectRole)
            delete_button.setAutoDefault(False)
            delete_button.setDefault(False)
            self.buttonBox.rejected.connect(lambda: self.delete_booking(booking, https_session))

        self.layout = QVBoxLayout()
        self.layout.addWidget(QLabel("<b><i>Booking info: </i></b>"), 0, Qt.AlignCenter)

        for info in booking_info_dialog:
            self.layout.addWidget(QLabel(f"<b>{info[0]} </b>" + str(info[1])))

        self.layout.addSpacing(20)

        self.layout.addWidget(self.buttonBox)
        self.setLayout(self.layout)


    def delete_booking(self, booking, https_session):
        reply = QMessageBox.question(self, 'Delete booking',
                                     "Are you sure to delete this booking?", QMessageBox.Yes |
                                     QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            response = make_http_request(https_session, "delete", "bookings/" + str(booking.get_id()))
            if response:
                QMessageBox.information(self, "Server response", response.text)
                self.reject()
        else:
            return


class Bookings(QWidget):
    def __init__(self, https_session, user, only_in_progress = False, only_expired = False):
        super().__init__()
        self.https_session = https_session
        self.only_in_progress = only_in_progress
        self.only_expired = only_expired
        self.user = user
        self.initUI()

    def initUI(self):
        self.is_admin = False
        booking_info = ["Datetime start", "Datetime end", "License plate", "Parking lot", "Slot number"]

        if user_is_admin(self.user, self.https_session):
            self.is_admin = True
            booking_info.insert(3, "User")

        vbox = QVBoxLayout()

        window_title = "Bookings in progress" if self.only_in_progress else "Bookings expired" if self.only_expired else "Bookings"

        text = QLabel(window_title)
        text.setStyleSheet("font-family: Ubuntu; font-size: 30px;")
        vbox.addWidget(text, 1, Qt.AlignTop | Qt.AlignHCenter)
        self.user_bookings_table = QTableWidget(0, len(booking_info)+1)
        hheader_labels = list(booking_info)
        hheader_labels.append("Details")
        self.user_bookings_table.setHorizontalHeaderLabels(hheader_labels)
        self.user_bookings_table.setEditTriggers(QAbstractItemView.NoEditTriggers)			# no editable

        self.user_bookings_table.horizontalHeader().setStretchLastSection(True);
        self.user_bookings_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch);

        vbox.addWidget(self.user_bookings_table, 9)
        vbox.addStretch(1)

        self.setLayout(vbox)

        self.setWindowTitle(window_title)
        self.show()


    def get_user_vehicles(self):
        if self.is_admin:
            request_relative_uri = "vehicles"
        else:
            request_relative_uri = "users/" + str(self.user.get_id()) + "/vehicles"

        response = make_http_request(self.https_session, "get", request_relative_uri)
        if response.json():
            self.user_vehicles = [Vehicle(**user_vehicle) for user_vehicle in response.json()]
        else:
            self.user_vehicles = []


    def get_vehicle_info(self, id_vehicle, only_license_plate = False):
        try:
            vehicle_index = self.user_vehicles.index(Vehicle(id = id_vehicle))
        except ValueError:
            return
        else:
            vehicle = self.user_vehicles[vehicle_index]
            if only_license_plate:
                return vehicle.get_license_plate()
            else:
                return vehicle


    def get_parking_lots(self):
        response = make_http_request(self.https_session, "get", "parking_lots")
        if response.json():
            self.parking_lots = [ParkingLot(**parking_lots) for parking_lots in response.json()]
        else:
            self.parking_lots = []
            return

        if self.parking_lots:                       # if list is empty -> false
            for parking_lot in self.parking_lots:
                # get info on parking slots of parking lot
                response = make_http_request(self.https_session, "get", "parking_lots/" + str(parking_lot.get_id()) + "/parking_slots")
                if response.json():
                    parking_lot.set_parking_slots([ParkingSlot(**parking_slot) for parking_slot in response.json()])


    def get_parking_slot_info(self, id_parking_slot):
        for parking_lot in self.parking_lots:
            try:
                parking_lot_slots = parking_lot.get_parking_slots()
                slot_index = parking_lot_slots.index(ParkingSlot(id = id_parking_slot))
                slot = parking_lot_slots[slot_index]
                # get parking lot name, street and parking slot number
                return (parking_lot.get_name(), parking_lot.get_street(), slot.get_number())
            except ValueError:
                continue
        return ("N/A","N/A","N/A")


    def get_users(self):
        response = make_http_request(self.https_session, "get", "users")
        if response.json():
            self.users = [User(**user) for user in response.json()]
        else:
            self.users = []


    def get_user_email(self, id_user):
        try:
            user_index = self.users.index(User(id = id_user))
            return self.users[user_index].get_email()
        except ValueError:
            return "N/A"


    def get_user_bookings(self):
        self.user_bookings_table.clearContents()
        self.user_bookings_table.setRowCount(0)

        now_datetime = datetime.now(timezone.utc)
        now = now_datetime.strftime("%Y-%m-%dT%H_%M_%S")
        utc_zone = tzutc()
        params = {}

        if self.only_in_progress:
            params["since"] = now
        elif self.only_expired:
            params["until"] = now
        else:
            pass                 #with no params set all bookings will be returned

        if not self.is_admin:
            params["id_user"] = self.user.get_id()

        response = make_http_request(self.https_session, "get", "bookings", params = params)

        if response.json():
            self.bookings = [Booking(**booking) for booking in response.json()]

            for i, booking in enumerate(self.bookings):

                if self.only_expired:
                    booking_end_datetime = datetime.strptime(booking.get_datetime_end(), "%Y-%m-%d %H:%M:%S")
                    booking_end_datetime = booking_end_datetime.replace(tzinfo=utc_zone)
                    if (booking_end_datetime - now_datetime).total_seconds() > 0:
                        continue

                booking_methods = [booking.get_datetime_start, booking.get_datetime_end, self.get_vehicle_info, self.get_parking_slot_info]

                if self.is_admin:
                    booking_methods.insert(3, self.get_user_email)

                # from UTC to local timezone
                booking.set_datetime_start(datetime_UTC_to_local(booking.get_datetime_start()))
                booking.set_datetime_end(datetime_UTC_to_local(booking.get_datetime_end()))
                if booking.get_entry_time():
                    booking.set_entry_time(datetime_UTC_to_local(booking.get_entry_time()))
                if booking.get_exit_time():
                    booking.set_exit_time(datetime_UTC_to_local(booking.get_exit_time()))

                self.user_bookings_table.insertRow(i)
                for j in range(self.user_bookings_table.columnCount() - 1):
                    method = booking_methods[j]
                    if j in [0,1]:
                        item = QTableWidgetItem(method())
                        item.setTextAlignment(Qt.AlignCenter)
                        self.user_bookings_table.setItem(i, j, item)
                    elif j == 2:
                        license_plate = method(booking.get_id_vehicle(), only_license_plate = True)
                        item = QTableWidgetItem(license_plate if license_plate else "N/A")
                        item.setTextAlignment(Qt.AlignCenter)
                        self.user_bookings_table.setItem(i, j, item)
                    elif j == 3 and self.is_admin:
                        vehicle = self.get_vehicle_info(booking.get_id_vehicle())
                        if vehicle:
                            id_user = vehicle.get_id_user()
                            item = QTableWidgetItem(method(id_user))
                        else:
                            item = QTableWidgetItem("N/A")
                        item.setTextAlignment(Qt.AlignCenter)
                        self.user_bookings_table.setItem(i, j, item)
                    else:
                        slot_info = method(booking.get_id_parking_slot())
                        item = QTableWidgetItem(slot_info[0])
                        item.setTextAlignment(Qt.AlignCenter)
                        self.user_bookings_table.setItem(i, j, item)
                        item = QTableWidgetItem(str(slot_info[2]))
                        item.setTextAlignment(Qt.AlignCenter)
                        self.user_bookings_table.setItem(i, j+1, item)
                        break


        for row in range(self.user_bookings_table.rowCount()):
            item = QPushButton("Show")
            self.user_bookings_table.setCellWidget(row, self.user_bookings_table.columnCount()-1, item)
            item.clicked.connect(lambda _,row=row: self.show_booking_details(row))


    def show_booking_details(self, row):
        booking = self.bookings[row]
        vehicle_info = self.get_vehicle_info(booking.get_id_vehicle())
        parking_slot_info = self.get_parking_slot_info(booking.get_id_parking_slot())
        details_dialog = DetailsDialog(self.user, booking, vehicle_info, parking_slot_info, self.https_session, self.only_expired, self)
        # if clicked OK button
        if details_dialog.exec_():
            pass
        else:
            self.get_user_bookings()


    def showEvent(self, event):
        self.get_user_vehicles()
        self.get_parking_lots()
        if self.is_admin:
            self.get_users()
        self.get_user_bookings()
