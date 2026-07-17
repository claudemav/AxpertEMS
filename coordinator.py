from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
class AxpertCoordinator(DataUpdateCoordinator):
    async def _async_update_data(self):
        return {}
