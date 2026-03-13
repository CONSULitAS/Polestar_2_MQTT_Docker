
# source for GQL string: https://github.com/evcc-io/evcc/blob/master/vehicle/polestar/query.gql
# und https://github.com/TA2k/ioBroker.polestar/blob/e4fc6fb693e7c904dd414beca4f452416233111f/main.js#L292
GET_CONSUMER_CARS_V2_QUERY = """
query GetConsumerCarsV2 {
    getConsumerCarsV2 {
        vin
        internalVehicleIdentifier
        registrationNo
        market
        originalMarket
        currentPlannedDeliveryDate
        deliveryDate
        edition
        pno34
        hasPerformancePackage
        modelYear
        # commercialModelYears
        computedModelYear
        structureWeek
        primaryDriver
        userIsPrimaryDriver
        content {
            exterior { code name description excluded }
            exteriorDetails { code name description excluded }
            interior { code name description excluded }
            performancePackage { code name description excluded }
            performanceOptimizationSpecification {
                power { value unit }
                torqueMax { value unit }
                acceleration { value unit description }
            }
            wheels { code name description excluded }
            plusPackage { code name description excluded }
            pilotPackage { code name description excluded }
            motor { name description excluded }
            model { name code }
            specification {
                battery
                bodyType
                brakes
                combustionEngine
                electricMotors
                performance
                suspension
                tireSizes
                torque
                totalHp
                totalKw
                trunkCapacity { label value }
            }
            dimensions {
                wheelbase { label value }
                groundClearanceWithPerformance { label value }
                groundClearanceWithoutPerformance { label value }
                dimensions { label value }
            }
            towbar { code name description excluded }
        }
    }
}
""".strip()

def build_getconsumercarsv2_payload():
    return {
        "query": GET_CONSUMER_CARS_V2_QUERY,
        "operationName": "GetConsumerCarsV2",
        "variables": "{}",
    }


CAR_TELEMATICS_V2_QUERY = """
query CarTelematicsV2($vins: [String!]!) {
    carTelematicsV2(vins: $vins) {
        health {
            vin
            brakeFluidLevelWarning
            daysToService
            distanceToServiceKm
            engineCoolantLevelWarning
            oilLevelWarning
            serviceWarning
            timestamp { seconds nanos }
        }
        battery {
            vin
            batteryChargeLevelPercentage
            chargingStatus
            estimatedChargingTimeToFullMinutes
            estimatedDistanceToEmptyKm
            timestamp { seconds nanos }
        }
        odometer {
            vin
            odometerMeters
            timestamp { seconds nanos }
        }
    }
}
""".strip()


def build_cartelematicsv2_payload(vin):
    return {
        "query": CAR_TELEMATICS_V2_QUERY,
        "operationName": "CarTelematicsV2",
        "variables": {"vins": vin},
    }
