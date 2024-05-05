import json
import time

from engine import *
from status import StatusMonitoringOpenOrders


class MonitoringOpenOrders:

    def __init__(self, client_bot, mailer_client, db):
        self.client = client_bot
        self.mailer = mailer_client
        self.db = db
        self.open_positions: list = []
        self.list_pair_open_positions: list = []
        self.status = StatusMonitoringOpenOrders(
            "MonitoringOpenOrders",
            amount_open_positions=len(self.open_positions)
        )

    def get_open_positions(self) -> list:
        checklist = []
        open_pos = self.client.futures_position_information()
        for i in open_pos:
            pair_entry_price = float(i["entryPrice"])
            if pair_entry_price > 0:
                checklist.append(i)
        return checklist

    def get_max_value_of_klines(self, pair) -> float:
        high_value = []
        klines = self.client.futures_continous_klines(pair=pair, contractType="PERPETUAL", interval="4h", limit=2)
        for kline in klines:
            high_value.append(float(kline[2]))
        return max(high_value)

    def get_close_order(self, pair) -> float:
        open_orders = self.client.futures_get_open_orders()
        open_pos = self.client.futures_position_information()
        for i in open_orders:
            if i["symbol"] == pair and i["side"] == "BUY":
                return float(i["stopPrice"])
        for position in open_pos:
            if position["symbol"] == pair:
                return float(position["markPrice"])

    def update_open_positions_info(self) -> None:
        keys_for_delete = set(self.status.open_orders_info.keys()) - set(self.list_pair_open_positions)
        if len(keys_for_delete) > 0:
            for key in keys_for_delete:
                self.status.open_orders_info.pop(key)

    def do_iteration(self):
        self.list_pair_open_positions.clear()
        for position in self.open_positions:
            self.list_pair_open_positions.append(position["symbol"])
            close_order_value = self.get_close_order(position["symbol"])
            max_value = self.get_max_value_of_klines(position["symbol"])
            if max_value * TARGET_RATIO_FOR_OPEN_ORDERS >= close_order_value:
                logger.info(f"Требуется корректировка {position['symbol']}")
                self.mailer.send_email_message(
                    f"Корректировка {position['symbol']}",
                    f"Требуется корректировка {position['symbol']}"
                )
            self.status.open_orders_info.update(
                {
                    position["symbol"]: {
                        "Цена входа": position["entryPrice"],
                        "Цена закрытия": close_order_value,
                        "Максимальная цена": max_value
                    }
                }
            )

    def start_monitoring_open_orders(self):
        while True:
            try:

                self.open_positions = self.get_open_positions()
                self.status.amount_open_positions = len(self.open_positions)

                if self.open_positions:
                    self.do_iteration()
                else:
                    self.status.open_orders_info = {}

                self.update_open_positions_info()

                self.db.update_monitoring_open_orders_data(
                    self.status.name,
                    self.status.amount_open_positions,
                    self.status.iterations_count,
                    json.dumps(self.status.open_orders_info)
                )

                self.status.iterations_count += 1
                time.sleep(MONITORING_OPEN_ORDERS_TIMEOUT)

            except Exception as _ex:
                logger.error(f"Ошибка: {self.__class__.__qualname__} {_ex}")
                time.sleep(TRY_TIMEOUT_IF_EXCEPT)
